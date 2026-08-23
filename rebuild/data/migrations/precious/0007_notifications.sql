-- In-app messages for a signed-in person. Right now the only kind is "a private
-- schedule of yours failed to run" -- shown the next time they open the app, with
-- a "run it now" button. Kept tiny on purpose: unread ones show, dismissed ones
-- don't.
CREATE TABLE notifications (
  id TEXT PRIMARY KEY,
  user_email TEXT NOT NULL,
  kind TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL DEFAULT '',
  schedule_id TEXT,
  status TEXT NOT NULL DEFAULT 'unread',
  created_at TEXT NOT NULL
);

CREATE INDEX idx_notifications_inbox ON notifications (user_email, status);
