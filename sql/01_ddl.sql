CREATE TABLE corp_master (
    corp_code       CHAR(8)      NOT NULL,
    corp_name       VARCHAR(200) NOT NULL,
    corp_eng_name   VARCHAR(300),
    stock_code      CHAR(6),
    modify_date     DATE,
    PRIMARY KEY (corp_code)
);