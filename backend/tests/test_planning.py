import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np
import pandas as pd
from pydantic import ValidationError
from app.data.adapter import DataAdapter, resample_monthly
from app.services import trend_engine, ensemble_engine, model_registry
from app.services.inventory_planning import build_lead_time_plan
from app.api.planning import ForecastRequest

class PlanningTests(unittest.TestCase):
    def setUp(self):
        self.frame=pd.DataFrame({'month':pd.date_range('2021-04-01',periods=48,freq='MS'),
            'value':1000+np.arange(48)*10+np.sin(np.arange(48)*np.pi/6)*100})

    def test_all_calendar_grains_conserve_totals(self):
        frame=pd.DataFrame({'month':['2024-01-01','2024-02-01','2024-03-01'],'value':[310.,290.,620.]})
        for grain in ('monthly','daily','weekly','quarterly','yearly'):
            result=resample_monthly(frame,grain)
            self.assertAlmostEqual(result.value.sum(),1220.)
            self.assertFalse(result.month.duplicated().any())
        daily=resample_monthly(frame,'daily')
        self.assertIn('2024-02-29',daily.month.tolist())
        self.assertEqual(len(daily),91)
        self.assertAlmostEqual(daily.loc[daily.month.str.startswith('2024-02'),'value'].sum(),290.)
        weekly=resample_monthly(frame,'weekly')
        self.assertTrue((pd.to_datetime(weekly.month).dt.dayofweek==0).all())

    def test_combined_filters_and_quiet_tail(self):
        rows=pd.DataFrame({'month':['2024-01-01','2024-02-01','2024-03-01'],
            'item':['a','a','b'],'customer':['c','d','c'],'revenue':[10.,20.,30.]})
        with patch.object(DataAdapter,'_get_base_data',return_value=rows):
            result=DataAdapter().get_series('item','a',filters={'customer':'c'})
            self.assertEqual(result.value.tolist(),[10.,0.,0.])

    def test_unknown_dimension_rejected(self):
        with self.assertRaises(ValueError):DataAdapter().get_series('invented')

    def test_trend_dates_intervals_original_unit_metrics(self):
        result=trend_engine.run_forecast(self.frame,horizon=8)
        self.assertEqual(result['status'],'ok')
        f=result['forecast']
        self.assertEqual(f['months'][0],'2025-04-01')
        self.assertEqual(len(f['point']),8)
        self.assertGreater(min(f['point']),1000)
        self.assertTrue(np.all(np.asarray(f['lower_90'])<=f['point']))
        self.assertTrue(np.all(np.asarray(f['upper_90'])>=f['point']))
        self.assertLess(result['diagnostics']['holdout_mae'],1e-8)

    def test_zero_series_is_finite(self):
        self.frame['value']=0.
        result=trend_engine.run_forecast(self.frame,horizon=12)
        self.assertEqual(result['forecast']['point'],[0.]*12)
        self.assertIsNone(result['diagnostics']['mase'])

    def test_rf_no_target_leakage_and_recursive_features(self):
        from app.services.randomforest_engine import FeatureEngineer,RandomForestConfig,ForecastGenerator
        config=RandomForestConfig()
        prepared={'target':np.arange(30,dtype=float),'timestamps':pd.date_range('2020-01-01',periods=30,freq='MS')}
        features=FeatureEngineer(config).engineer(prepared)
        self.assertEqual(features['features'][0,features['feature_names'].index('roll_mean_3')],10.)
        class LagModel:
            def predict(self,row):return row[:,features['feature_names'].index('lag_1')]+1
        result=ForecastGenerator(config).forecast(LagModel(),features,prepared,3)
        self.assertEqual(result['point'],[30.,31.,32.])

    def test_lstm_log_scale_and_zero_targets(self):
        from app.services.lstm_engine import make_sequences,lstm_predict_recursive
        y=np.array([0.,1e8,2e8,0.,3e8,4e8,5e8,0.])
        x,_,targets,_=make_sequences(y,'log',{'lookback':3})
        self.assertTrue(np.isfinite(x).all())
        self.assertLess(x.max(),25)
        self.assertIn(0.,targets)
        with patch('app.services.lstm_engine.predict_ensemble',return_value=np.array([np.log1p(1e8)])):
            result=lstm_predict_recursive([],y,2,'log',{'lookback':3})
        np.testing.assert_allclose(result,[1e8,1e8])

    def test_ensemble_renormalizes_failed_members(self):
        def member(name,frame,horizon,fast=True):
            if name=='xgboost':return {'status':'unavailable','message':'missing runtime'}
            return trend_engine.run_forecast(frame,horizon=horizon)
        with patch.object(ensemble_engine,'run_member',side_effect=member):
            result=ensemble_engine.run_ensemble_forecast(self.frame,horizon=3)
        self.assertAlmostEqual(sum(result['weights'].values()),1)
        self.assertNotIn('xgboost',result['weights'])
        self.assertTrue(all(v>=.05 for v in result['weights'].values()))
        self.assertEqual(result['members']['trend']['validation']['folds'],2)
        self.assertEqual(len(result['forecast']['point']),3)

    def test_request_validation(self):
        for params in ({'horizon':0},{'dimension':'vendor'},{'filters':{'bogus':'x'}},{'granularity':'yearly','horizon':11}):
            with self.assertRaises(ValidationError):ForecastRequest(**params)

    def test_registry_rollback_and_path_validation(self):
        with tempfile.TemporaryDirectory() as folder,patch.object(model_registry,'ROOT',Path(folder)):
            a=model_registry.record({'model':'trend'},{'status':'ok','data_fingerprint':'one'})
            b=model_registry.record({'model':'trend'},{'status':'ok','data_fingerprint':'two'})
            model_registry.activate(a)
            self.assertEqual(next(iter(model_registry.list_series().values()))['active'],a)
            self.assertFalse(model_registry.compare(a,b)['same_data'])
            with self.assertRaises(ValueError):model_registry.get_revision('../secrets')

    def test_classifier_no_fabricated_probabilities(self):
        from app.services import classifier_runtime
        with tempfile.TemporaryDirectory() as folder,patch.object(classifier_runtime,'ROOT',Path(folder)):
            result=classifier_runtime.predict('nn')
            self.assertEqual(result['status'],'unavailable')
            self.assertEqual(result['predictions'],[])

    def test_lead_time_plan_uses_source_months_and_explicit_inputs(self):
        frame = pd.DataFrame({
            'month': pd.date_range('2024-01-01', periods=12, freq='MS').tolist() * 2,
            'item': ['A'] * 12 + ['B'] * 12,
            'actual_units': [100] * 12 + [0] * 9 + [50, 50, 50],
        })
        result = build_lead_time_plan(frame, lead_time_days=30, safety_stock_months=1,
                                      coverage_months=2, limit=2, as_of='2024-12-31')
        self.assertEqual(result['source_as_of'], '2024-12-31')
        self.assertEqual(result['rows'][0]['key'], 'A')
        row = result['rows'][0]
        self.assertGreater(row['lead_time_demand_units'], 0)
        self.assertEqual(row['status'], 'Order now')
        self.assertEqual(row['expected_arrival_date'], '2025-01-30')
        self.assertGreater(row['suggested_order_units'], row['lead_time_demand_units'])

if __name__=='__main__':unittest.main()
