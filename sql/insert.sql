SET time_zone = '+00:00';
-- INSERT INTO Airline (name) VALUES 
-- ('JetBlue');

-- INSERT INTO Airport (code, city, country, airport_type) VALUES 
-- ('JFK', 'New York', 'USA', 'International'),
-- ('PVG', 'Shanghai', 'China', 'International'),
-- ('BOS', 'Boston', 'USA', 'International'),
-- ('PEK', 'Beijing', 'China', 'International'),
-- ('LAX', 'LOS Angeles', 'USA', 'Domestic'),
-- ('SFO', 'San Francisco', 'USA', 'Domestic');


-- INSERT INTO Customer (email, name, password, building_number, street, city, state, phone_number, passport_number, passport_expiration, passport_country, date_of_birth) VALUES 
-- ('zl3419@nyu.edu', 'Eric Lin', 'root', '101', 'Main St', 'New York', 'NY', '555-1234', 'A12345678', '2028-05-15', 'USA', '1990-10-01'),
-- ('hw3345@nyu.edu', 'Keith Wang', 'root', '20', 'Oak Ave', 'Boston', 'MA', '555-5678', 'B98765432', '2027-11-20', 'USA', '1985-03-25');

-- INSERT INTO Airline_Staff (username, password, first_name, last_name, date_of_birth, email_address, airline_name) VALUES
-- ('jbsmith', '3321-4498', 'John', 'Smith', '1975-01-20', 'john.smith@jetblue.com', 'JetBlue');

-- INSERT INTO Airline_Staff_Phone (username, phone) VALUES
-- ('jbsmith', '954-555-0001'),
-- ('jbsmith', '954-555-0002');

-- INSERT INTO Airplane (id_number, airline_name, seats, manufacturer, age) VALUES 
-- ('N603JB', 'JetBlue', 162, 'Airbus', 5),
-- ('N500JB', 'JetBlue', 130, 'Embraer', 10),
-- ('N701JB', 'JetBlue', 200, 'Airbus', 2),
-- ('N111JB', 'JetBlue', 145, 'Airbus', 6),
-- ('N222JB', 'JetBlue', 102, 'Embraer', 3);

-- INSERT INTO Flight (airline_name, flight_number, departure_date_time, arrival_date_time, base_price, departure_airport, arrival_airport, airplane_id_number, status) VALUES 
-- ('JetBlue', 'B6008', '2026-03-01 10:00:00', '2026-03-02 12:00:00', 850.50, 'JFK', 'PVG', 'N603JB', 'DELAYED');

-- INSERT INTO Flight (airline_name, flight_number, departure_date_time, arrival_date_time, base_price, departure_airport, arrival_airport, airplane_id_number, status) VALUES 
-- ('JetBlue', 'B6009', '2025-10-20 08:00:00', '2025-10-20 11:00:00', 820.00, 'PVG', 'JFK', 'N701JB', 'ON_TIME');

-- INSERT INTO Flight (airline_name, flight_number, departure_date_time, arrival_date_time, base_price, departure_airport, arrival_airport, airplane_id_number, status) VALUES 
-- ('JetBlue', 'B6010', '2025-12-20 08:00:00', '2025-12-21 9:00:00', 199.00, 'BOS', 'PEK', 'N111JB', 'ON_TIME');

-- INSERT INTO Flight (airline_name, flight_number, departure_date_time, arrival_date_time, base_price, departure_airport, arrival_airport, airplane_id_number, status) VALUES 
-- ('JetBlue', 'B6011', '2025-12-27 12:00:00', '2025-12-28 13:00:00', 79.00, 'LAX', 'SFO', 'N222JB', 'CANCELLED');

-- INSERT INTO Ticket (ticket_ID, customer_email, airline_name, flight_number, departure_date_time, card_type, card_number, name_on_card, expiration_date, purchase_date_time) VALUES 
-- (1001, 'zl3419@nyu.edu', 'JetBlue', 'B6008', '2026-03-01 10:00:00', 'Credit', '1111222233334444', 'Eric Lin', '2027-10-01', '2025-10-28 14:00:00');

-- INSERT INTO Ticket (ticket_ID, customer_email, airline_name, flight_number, departure_date_time, card_type, card_number, name_on_card, expiration_date, purchase_date_time) VALUES 
-- (1002, 'hw3345@nyu.edu', 'JetBlue', 'B6009', '2025-10-20 08:00:00', 'Debit', '5555666677778888', 'Keith Wang', '2028-02-01', '2025-10-28 15:30:00');

-- INSERT INTO Review (customer_email, airline_name, flight_number, departure_date_time, rating, comment, created_at) VALUES 
-- ('hw3345@nyu.edu', 'JetBlue', 'B6009', '2025-10-20 08:00:00', 4, 'Service was good, but the seat was uncomfortable.', '2025-10-21 12:00:00');



INSERT INTO Airline (name) VALUES 
('United');

INSERT INTO Airline_Staff (username, password, first_name, last_name, date_of_birth, email_address, airline_name) VALUES
('admin', 'abcd', 'Roe', 'Jones', '1978-05-25', 'staff@nyu.edu', 'United');

INSERT INTO Airplane (id_number, airline_name, seats, manufacturer, age) VALUES 
('1', 'United', 4, 'Boeing', 10),
('2', 'United', 4, 'Airbus', 12),
('3', 'United', 50, 'Boeing', 8);

INSERT INTO Airline_Staff_Phone (username, phone) VALUES
('admin', '111-2222-3333'),
('admin', '444-5555-6666');

INSERT INTO Airport(code, city, country, airport_type) VALUES
('JFK',  'NYC',         'USA',   'Both'),
('BOS',  'Boston',      'USA',   'Both'),
('PVG',  'Shanghai',    'China', 'Both'),
('BEI',  'Beijing',     'China', 'Both'),
('SFO',  'San Francisco','USA',  'Both'),
('LAX',  'Los Angeles', 'USA',   'Both'),
('HKA',  'Hong Kong',   'China', 'Both'),
('SZX',  'Shenzhen',    'China', 'Both');

INSERT INTO Customer(email, name, password, building_number, street, city, state, phone_number, passport_number, passport_expiration, passport_country, date_of_birth)
VALUES
('testcustomer@nyu.edu', 'Jon Snow',    '1234',   '1555', 'Jay St',  'Brooklyn','NY',  '123-4321-4321', '54321', '2025-12-24', 'USA', '1999-12-19'),
('user1@nyu.edu',        'Alice Bob',   '1234',   '5405', 'Jay St',  'Brooklyn','NY',  '123-4322-4322', '54322', '2025-12-25', 'USA', '1999-11-19'),
('user3@nyu.edu',        'Trudy Jones', '1234',   '1890', 'Jay St',  'Brooklyn','NY',  '123-4324-4324', '54324', '2025-09-24', 'USA', '1999-09-19');

INSERT INTO Flight(airline_name, flight_number, departure_date_time, arrival_date_time, base_price, departure_airport, arrival_airport, airplane_id_number, status)
VALUES
('United','102','2025-09-14 13:25:25','2025-09-14 16:50:25', 300, 'SFO','LAX','3','ON_TIME'),
('United','104','2025-10-14 13:25:25','2025-10-14 16:50:25', 300, 'PVG','BEI','3','ON_TIME'),
('United','206','2026-01-04 13:25:25','2026-01-04 16:50:25', 350, 'SFO','LAX','2','ON_TIME'),
('United','207','2026-02-05 13:25:25','2026-02-05 16:50:25', 300, 'LAX','SFO','2','ON_TIME'),
('United','296','2025-12-28 13:25:25','2025-12-28 16:50:25',3000, 'PVG','SFO','1','ON_TIME'),
('United','715','2025-09-25 10:25:25','2025-09-25 13:50:25', 500, 'PVG','BEI','1','DELAYED');

INSERT INTO Ticket
(ticket_ID, customer_email, airline_name, flight_number, departure_date_time, card_type, card_number,  name_on_card, expiration_date, purchase_date_time)
VALUES
(1,  'testcustomer@nyu.edu', 'United','102','2025-09-14 13:25:25','Credit','1111-2222-3333-4444','Test Customer 1','2026-03-01','2025-08-15 11:55:55'),
(2,  'user1@nyu.edu',        'United','102','2025-09-14 13:25:25','Credit','1111-2222-3333-5555','User 1',         '2026-03-01','2025-08-20 11:55:55'),
(3,  'user1@nyu.edu',        'United','104','2025-10-14 13:25:25','Credit','1111-2222-3333-5555','User 1',         '2026-03-01','2025-09-21 11:55:55'),
(4,  'testcustomer@nyu.edu', 'United','104','2025-10-14 13:25:25','Credit','1111-2222-3333-4444','Test Customer 1','2027-03-01','2025-09-28 11:55:55'),
(5,  'user3@nyu.edu',        'United','102','2025-09-14 13:25:25','Credit','1111-2222-3333-5555','User 3',         '2026-03-01','2025-07-16 11:55:55'),
(6,  'testcustomer@nyu.edu', 'United','715','2025-09-25 10:25:25','Credit','1111-2222-3333-4444','Test Customer 1','2026-03-01','2024-09-20 11:55:55'),
(7,  'user3@nyu.edu',        'United','206','2026-01-04 13:25:25','Credit','1111-2222-3333-5555','User 3',         '2026-03-01','2025-11-20 11:55:55'),
(8,  'user1@nyu.edu',        'United','206','2026-01-04 13:25:25','Credit','1111-2222-3333-5555','User 1',         '2026-03-01','2025-10-21 11:55:55'),
(9,  'user1@nyu.edu',        'United','207','2026-02-05 13:25:25','Credit','1111-2222-3333-5555','User 1',         '2026-03-01','2025-12-02 11:55:55'),
(10, 'testcustomer@nyu.edu', 'United','207','2026-02-05 13:25:25','Credit','1111-2222-3333-4444','Test Customer 1','2026-03-01','2025-10-25 11:55:55'),
(11, 'user1@nyu.edu',        'United','296','2025-12-28 13:25:25','Credit','1111-2222-3333-4444','Test Customer 1','2026-03-01','2025-10-22 11:55:55'),
(12, 'testcustomer@nyu.edu', 'United','296','2025-12-28 13:25:25','Credit','1111-2222-3333-4444','Test Customer 1','2026-03-01','2025-11-20 11:55:55');

INSERT INTO Review
(customer_email, airline_name, flight_number, departure_date_time, rating, comment, created_at)
VALUES
('testcustomer@nyu.edu','United','102','2025-09-14 13:25:25',4,'Very Comfortable',                                   NOW()),
('user1@nyu.edu',      'United','102','2025-09-14 13:25:25',5,'Relaxing, check-in and onboarding very professional', NOW()),
('testcustomer@nyu.edu','United','104','2025-10-14 13:25:25',1,'Customer Care services are not good',                NOW()),
('user1@nyu.edu',      'United','104','2025-10-14 13:25:25',5,'Comfortable journey and Professional',                NOW());

