CREATE TABLE Airline (
    name VARCHAR(100) PRIMARY KEY
);

CREATE TABLE Airport (
    code CHAR(3) PRIMARY KEY,
    city VARCHAR(100),
    country VARCHAR(100),
    airport_type VARCHAR(50) CHECK (airport_type IN ('International', 'Domestic', 'Both'))
);

CREATE TABLE Airplane (
    id_number VARCHAR(20),
    airline_name VARCHAR(100),
    seats INT,
    manufacturer VARCHAR(100),
    age INT,
    PRIMARY KEY (id_number, airline_name),
    FOREIGN KEY (airline_name) REFERENCES Airline(name)
);

CREATE TABLE Flight (
    airline_name VARCHAR(100),
    flight_number VARCHAR(10),
    departure_date_time TIMESTAMP,
    arrival_date_time TIMESTAMP,
    base_price DECIMAL(10, 2),
    departure_airport CHAR(3),
    arrival_airport CHAR(3),
    airplane_id_number VARCHAR(20),
    status VARCHAR(50) CHECK (status IN ('ON_TIME', 'DELAYED', 'CANCELLED')), 
    PRIMARY KEY (airline_name, flight_number, departure_date_time),
    FOREIGN KEY (airline_name) REFERENCES Airline(name),
    FOREIGN KEY (departure_airport) REFERENCES Airport(code),
    FOREIGN KEY (arrival_airport) REFERENCES Airport(code),
    FOREIGN KEY (airplane_id_number, airline_name) REFERENCES Airplane(id_number, airline_name)
);

CREATE TABLE Customer (
    email VARCHAR(100) PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    password VARCHAR(100) NOT NULL,
    building_number VARCHAR(10),
    street VARCHAR(100),
    city VARCHAR(100),
    state VARCHAR(50),
    phone_number VARCHAR(20),
    passport_number VARCHAR(20),
    passport_expiration DATE,
    passport_country VARCHAR(100),
    date_of_birth DATE
);

CREATE TABLE Airline_Staff (
    username VARCHAR(50) PRIMARY KEY,
    password VARCHAR(100) NOT NULL,
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    date_of_birth DATE,
    email_address VARCHAR(100) UNIQUE,
    airline_name VARCHAR(100),
    FOREIGN KEY (airline_name) REFERENCES Airline(name)
);

CREATE TABLE Airline_Staff_Phone (
    username VARCHAR(50),
    phone VARCHAR(20),
    PRIMARY KEY (username, phone),
    FOREIGN KEY (username) REFERENCES Airline_Staff(username)
);

CREATE TABLE Ticket (
    ticket_ID INT PRIMARY KEY,
    customer_email VARCHAR(100),
    airline_name VARCHAR(100),
    flight_number VARCHAR(10),
    departure_date_time TIMESTAMP,
    card_type VARCHAR(50) CHECK (card_type in("Debit", "Credit")),
    card_number VARCHAR(20),
    name_on_card VARCHAR(100),
    expiration_date DATE,
    purchase_date_time TIMESTAMP,
    FOREIGN KEY (customer_email) REFERENCES Customer(email),
    FOREIGN KEY (airline_name, flight_number, departure_date_time) REFERENCES Flight(airline_name, flight_number, departure_date_time)
);

CREATE TABLE Review (
    customer_email VARCHAR(100),
    airline_name VARCHAR(100),
    flight_number VARCHAR(10),
    departure_date_time TIMESTAMP,
    rating INT CHECK (rating > 0 and rating < 6),
    comment TEXT,
    created_at TIMESTAMP,
    PRIMARY KEY (customer_email, airline_name, flight_number, departure_date_time),
    FOREIGN KEY (customer_email) REFERENCES Customer(email),
    FOREIGN KEY (airline_name, flight_number, departure_date_time) REFERENCES Flight(airline_name, flight_number, departure_date_time)
);

