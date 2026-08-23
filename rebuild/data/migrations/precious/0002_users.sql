-- People who have signed in. Role is resolved at login from the configured
-- developer list; this table is the app's own record of who has access and is
-- the display/admin source later. Email is the stable identity.

CREATE TABLE users (
  email TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  role TEXT NOT NULL,
  first_seen TEXT NOT NULL,
  last_seen TEXT NOT NULL
);
