/*
Creates the GlobalPartners SQL Server source database and tables.

The script does not drop or replace existing tables. This allows it to be
rerun safely during the initial setup.
*/

IF DB_ID(N'globalpartners') IS NULL
BEGIN
    EXEC(N'CREATE DATABASE globalpartners');
END;
GO

USE globalpartners;
GO

IF OBJECT_ID(N'dbo.order_items', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.order_items (
        app_name               NVARCHAR(100)  NOT NULL,
        restaurant_id          VARCHAR(50)    NOT NULL,
        creation_time_utc      DATETIME2(3)   NOT NULL,
        order_id               VARCHAR(50)    NOT NULL,
        user_id                VARCHAR(50)    NULL,
        printed_card_number    VARCHAR(20)    NULL,
        is_loyalty             BIT            NOT NULL,
        currency               CHAR(3)        NOT NULL,
        lineitem_id            VARCHAR(50)    NULL,
        item_category          NVARCHAR(150)  NULL,
        item_name              NVARCHAR(150)  NULL,
        item_price             DECIMAL(12, 2) NOT NULL,
        item_quantity          INT            NOT NULL
    );
END;
GO

IF OBJECT_ID(N'dbo.order_item_options', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.order_item_options (
        order_id               VARCHAR(50)    NOT NULL,
        lineitem_id            VARCHAR(50)    NOT NULL,
        option_group_name      NVARCHAR(100)  NOT NULL,
        option_name            NVARCHAR(150)  NOT NULL,
        option_price           DECIMAL(12, 2) NOT NULL,
        option_quantity        INT            NOT NULL
    );
END;
GO

IF OBJECT_ID(N'dbo.date_dim', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.date_dim (
        date_key               DATE           NOT NULL,
        year                   SMALLINT       NOT NULL,
        month                  TINYINT        NOT NULL,
        week                   TINYINT        NOT NULL,
        day_of_week            VARCHAR(10)    NOT NULL,
        is_weekend             BIT            NOT NULL,
        is_holiday             BIT            NOT NULL,
        holiday_name           NVARCHAR(100)  NULL,
        CONSTRAINT pk_date_dim PRIMARY KEY (date_key)
    );
END;
GO