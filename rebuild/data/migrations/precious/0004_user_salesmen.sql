-- Which salesman number(s) a signed-in person is scoped to. An admin manages
-- this list. A person who has rows here sees ONLY those salesmen's data; a
-- privileged user (admin/developer) sees everything and needs no rows here.
-- A non-privileged person with no rows here can't run reports (they'd see
-- nothing anyway). Email is stored lower-cased to match the users table.

CREATE TABLE user_salesmen (
  user_email TEXT NOT NULL,
  salesman_number TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (user_email, salesman_number)
);
