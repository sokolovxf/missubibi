-- MySQL dump 10.13  Distrib 26.7.0, for macos26.6 (arm64)
--
-- Host: localhost    Database: missubibi
-- ------------------------------------------------------
-- Server version	26.7.0

/*!40101 SET @OLD_CHARACTER_SET_CLIENT=@@CHARACTER_SET_CLIENT */;
/*!40101 SET @OLD_CHARACTER_SET_RESULTS=@@CHARACTER_SET_RESULTS */;
/*!40101 SET @OLD_COLLATION_CONNECTION=@@COLLATION_CONNECTION */;
/*!50503 SET NAMES utf8mb4 */;
/*!40103 SET @OLD_TIME_ZONE=@@TIME_ZONE */;
/*!40103 SET TIME_ZONE='+00:00' */;
/*!40014 SET @OLD_UNIQUE_CHECKS=@@UNIQUE_CHECKS, UNIQUE_CHECKS=0 */;
/*!40014 SET @OLD_FOREIGN_KEY_CHECKS=@@FOREIGN_KEY_CHECKS, FOREIGN_KEY_CHECKS=0 */;
/*!40101 SET @OLD_SQL_MODE=@@SQL_MODE, SQL_MODE='NO_AUTO_VALUE_ON_ZERO' */;
/*!40111 SET @OLD_SQL_NOTES=@@SQL_NOTES, SQL_NOTES=0 */;

--
-- Table structure for table `Customerfile_Data`
--

DROP TABLE IF EXISTS `Customerfile_Data`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Customerfile_Data` (
  `customerfile_customer_internal_id` int DEFAULT NULL,
  `customerfile_company_name` varchar(255) DEFAULT NULL,
  `customerfile_customer_type` varchar(50) DEFAULT NULL,
  `customerfile_fa_sub_industries` varchar(255) DEFAULT NULL,
  `customerfile_is_duplicate_customer` tinyint(1) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Itemfile_Data`
--

DROP TABLE IF EXISTS `Itemfile_Data`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Itemfile_Data` (
  `itemfile_item_internal_id` int DEFAULT NULL,
  `itemfile_item_code` varchar(100) DEFAULT NULL,
  `itemfile_production_status` varchar(50) DEFAULT NULL,
  `itemfile_product_category_1` varchar(100) DEFAULT NULL,
  `itemfile_product_category_2` varchar(100) DEFAULT NULL,
  `itemfile_list_price` decimal(12,2) DEFAULT NULL,
  `itemfile_is_missing_price` tinyint(1) DEFAULT NULL,
  `itemfile_is_duplicate_item` tinyint(1) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Table structure for table `Sales_Order_Merged`
--

DROP TABLE IF EXISTS `Sales_Order_Merged`;
/*!40101 SET @saved_cs_client     = @@character_set_client */;
/*!50503 SET character_set_client = utf8mb4 */;
CREATE TABLE `Sales_Order_Merged` (
  `so_internal_id` int DEFAULT NULL,
  `sales_order_date` date DEFAULT NULL,
  `sales_order_number` varchar(100) DEFAULT NULL,
  `sales_order_status` varchar(50) DEFAULT NULL,
  `customer_internal_id` int DEFAULT NULL,
  `company_name` varchar(255) DEFAULT NULL,
  `item_internal_id` int DEFAULT NULL,
  `item_code` varchar(100) DEFAULT NULL,
  `base_price` decimal(12,2) DEFAULT NULL,
  `quantity` int DEFAULT NULL,
  `is_completely_blank` tinyint(1) DEFAULT NULL,
  `is_duplicate_row` tinyint(1) DEFAULT NULL,
  `customer_type` varchar(50) DEFAULT NULL,
  `fa_sub_industries` varchar(255) DEFAULT NULL,
  `production_status` varchar(50) DEFAULT NULL,
  `product_category_1` varchar(100) DEFAULT NULL,
  `product_category_2` varchar(100) DEFAULT NULL,
  `list_price` decimal(12,2) DEFAULT NULL,
  `unmatched_customer` tinyint(1) DEFAULT NULL,
  `unmatched_item` tinyint(1) DEFAULT NULL,
  `calendar_year` int DEFAULT NULL,
  `month_name` varchar(20) DEFAULT NULL,
  `total_revenue_thb` decimal(15,2) DEFAULT NULL,
  `list_revenue_thb` decimal(15,2) DEFAULT NULL,
  `discount_thb` decimal(15,2) DEFAULT NULL,
  `discount_pct` decimal(8,4) DEFAULT NULL,
  `fiscal_year` varchar(10) DEFAULT NULL,
  `fiscal_quarter` varchar(10) DEFAULT NULL,
  `season` varchar(20) DEFAULT NULL,
  `year_month` varchar(10) DEFAULT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci;
/*!40101 SET character_set_client = @saved_cs_client */;

--
-- Dumping routines for database 'missubibi'
--
/*!40103 SET TIME_ZONE=@OLD_TIME_ZONE */;

/*!40101 SET SQL_MODE=@OLD_SQL_MODE */;
/*!40014 SET FOREIGN_KEY_CHECKS=@OLD_FOREIGN_KEY_CHECKS */;
/*!40014 SET UNIQUE_CHECKS=@OLD_UNIQUE_CHECKS */;
/*!40101 SET CHARACTER_SET_CLIENT=@OLD_CHARACTER_SET_CLIENT */;
/*!40101 SET CHARACTER_SET_RESULTS=@OLD_CHARACTER_SET_RESULTS */;
/*!40101 SET COLLATION_CONNECTION=@OLD_COLLATION_CONNECTION */;
/*!40111 SET SQL_NOTES=@OLD_SQL_NOTES */;

-- Dump completed on 2026-09-06 22:27:35
