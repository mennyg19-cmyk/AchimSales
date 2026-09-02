-- Access may point at a customer_master SalesGroup that is not in `salesmen`.
-- Keep the users FK; drop the salesmen FK so we do not stub rows into a table
-- we are retiring.
CREATE TABLE user_salesman_access_new (
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    salesman_key TEXT NOT NULL,
    PRIMARY KEY (user_id, salesman_key)
);
INSERT INTO user_salesman_access_new(user_id, salesman_key)
    SELECT user_id, salesman_key FROM user_salesman_access;
DROP TABLE user_salesman_access;
ALTER TABLE user_salesman_access_new RENAME TO user_salesman_access;
