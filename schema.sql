CREATE TABLE IF NOT EXISTS sent_posts (
    user_id INTEGER,
    post_hash TEXT,
    sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, post_hash)
);