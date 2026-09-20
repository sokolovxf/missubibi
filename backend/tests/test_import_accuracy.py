import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from sqlalchemy import create_engine
from app.services import csv_import, ensemble_engine
from app.data.adapter import adapter

class ImportAccuracyTests(unittest.TestCase):
    def test_preview_validation_and_aliases(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(csv_import,'ROOT',Path(directory)):
            valid=csv_import.preview(b'year_month,sku,quantity,total_revenue_thb\n2025-04,A,2,100\n','sales.csv')
            self.assertEqual(valid['errors'],[])
            self.assertEqual(valid['sample'][0]['month'],'2025-04-01')
            invalid=csv_import.preview(b'month,item,actual_units,revenue\nbad,A,no,100\n','bad.csv')
            self.assertEqual(len(invalid['errors']),2)
            self.assertIsNone(invalid['period_start'])
            self.assertFalse((Path(directory)/f"{invalid['token']}.json").exists())
            self.assertTrue(csv_import.preview(b'item,vendor\nA,one\nA,two\n','vendor.csv')['errors'])

    def test_import_idempotence_replace_and_vendor_mapping(self):
        with tempfile.TemporaryDirectory() as directory:
            engine=create_engine('sqlite:///'+directory+'/imports.db')
            with patch.object(csv_import,'ROOT',Path(directory)),patch.object(csv_import,'engine',engine),patch.object(adapter,'invalidate'),patch.object(adapter,'_get_base_data',return_value=pd.DataFrame(columns=csv_import.COLUMNS)):
                first=csv_import.preview(b'month,item,actual_units,revenue\n2025-04,A,2,100\n','a.csv')
                result=csv_import.commit(first['token'],'append')
                self.assertEqual(csv_import.commit(first['token'],'append'),result)
                base,rows,_=csv_import.load_overlay()
                self.assertTrue(base);self.assertEqual(len(rows),1)
                second=csv_import.preview(b'month,item,actual_units,revenue\n2025-05,B,3,200\n','b.csv')
                csv_import.commit(second['token'],'replace')
                base,rows,_=csv_import.load_overlay()
                self.assertFalse(base);self.assertEqual(rows.item.tolist(),['B'])
                mapping=csv_import.preview(b'item,vendor\nB,Vendor B\n','vendors.csv')
                csv_import.commit(mapping['token'],'append')
                self.assertEqual(csv_import.load_overlay()[2],{'B':'Vendor B'})
            engine.dispose()

    def test_wape_and_undefined_zero_denominator(self):
        frame=pd.DataFrame({'month':pd.date_range('2021-01-01',periods=48,freq='MS'),'value':[100.]*48})
        def predict(name,train,horizon,fast):
            return {'status':'ok','forecast':{'months':pd.date_range(pd.Timestamp(train.month.iloc[-1])+pd.offsets.MonthBegin(),periods=horizon,freq='MS').astype(str).tolist(),'point':[80.]*horizon}}
        with patch.object(ensemble_engine,'run_member',side_effect=predict):
            result=ensemble_engine.evaluate_member('trend',frame)
            self.assertEqual(result['accuracy_pct'],80.)
            self.assertEqual(result['wape_pct'],20.)
            frame['value']=0.
            self.assertIsNone(ensemble_engine.evaluate_member('trend',frame)['accuracy_pct'])
