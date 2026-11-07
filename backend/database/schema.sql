-- user table
CREATE TABLE IF NOT EXISTS users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username TEXT NOT NULL,
    hashed_pwd TEXT NOT NULL,
    UNIQUE (username)
);

-- index for username search
CREATE INDEX IF NOT EXISTS idx_username 
    ON users(username);

-- question table
CREATE TABLE IF NOT EXISTS questions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name TEXT NOT NULL,
    topic TEXT,
    difficulty TEXT NOT NULL,
    source TEXT,
    labels TEXT,
    UNIQUE (name)
);

-- lists table
CREATE TABLE IF NOT EXISTS lists (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, name)
);

-- list question table
CREATE TABLE IF NOT EXISTS list_questions (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    list_id BIGINT NOT NULL REFERENCES lists(id) ON DELETE CASCADE,
    question_id BIGINT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    UNIQUE (list_id, question_id)
);

-- child table for attempts
CREATE TABLE IF NOT EXISTS attempts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    question_id BIGINT NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    body TEXT NOT NULL,
    proficiency TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- index for searching attempts by user_id and question_id
CREATE INDEX IF NOT EXISTS idx_attempts_user_question
    ON attempts (user_id, question_id);

-- index for search by name
CREATE INDEX IF NOT EXISTS idx_name
    ON questions (name);

-- index for search by topic
CREATE INDEX IF NOT EXISTS idx_topic
    ON questions (topic);

-- index for search by difficulty
CREATE INDEX IF NOT EXISTS idx_difficulty
    ON questions (difficulty);

-- index for finding all the attempts for the selected question
CREATE INDEX IF NOT EXISTS idx_question_id
    ON attempts (question_id);
