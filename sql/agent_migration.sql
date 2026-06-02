CREATE TABLE IF NOT EXISTS agent_sessions (
    id VARCHAR(80) PRIMARY KEY,
    role VARCHAR(20) NOT NULL,
    principal VARCHAR(120) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS agent_traces (
    id INT AUTO_INCREMENT PRIMARY KEY,
    session_id VARCHAR(80) NOT NULL,
    role VARCHAR(20) NOT NULL,
    principal VARCHAR(120) NOT NULL,
    user_message TEXT NOT NULL,
    reasoning TEXT,
    tool_calls TEXT,
    final_answer TEXT,
    latency_ms INT,
    error TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS booking_intents (
    id INT AUTO_INCREMENT PRIMARY KEY,
    customer_email VARCHAR(100) NOT NULL,
    airline_name VARCHAR(100) NOT NULL,
    flight_number VARCHAR(10) NOT NULL,
    departure_date_time TIMESTAMP NOT NULL,
    status VARCHAR(40) NOT NULL DEFAULT 'PENDING_CONFIRMATION',
    idempotency_key VARCHAR(80),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    confirmed_at TIMESTAMP NULL,
    ticket_id INT NULL,
    UNIQUE KEY uniq_booking_intent_idempotency (customer_email, idempotency_key)
);

CREATE TABLE IF NOT EXISTS user_preferences (
    customer_email VARCHAR(100) PRIMARY KEY,
    departure_city VARCHAR(100),
    destination_city VARCHAR(100),
    max_budget DECIMAL(10, 2),
    preferred_airline VARCHAR(100),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS ticket_cancellations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ticket_id INT NOT NULL,
    customer_email VARCHAR(100) NOT NULL,
    airline_name VARCHAR(100) NOT NULL,
    flight_number VARCHAR(10) NOT NULL,
    departure_date_time TIMESTAMP NOT NULL,
    flight_status_at_cancellation VARCHAR(50) NOT NULL,
    base_price DECIMAL(10, 2) NOT NULL,
    cancellation_fee DECIMAL(10, 2) NOT NULL,
    refund_amount DECIMAL(10, 2) NOT NULL,
    policy_code VARCHAR(40) NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_ticket_cancellation (ticket_id, customer_email)
);
