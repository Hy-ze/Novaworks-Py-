CREATE DATABASE IF NOT EXISTS novaworks;
USE novaworks;

CREATE TABLE IF NOT EXISTS users (
  id VARCHAR(10) PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  email VARCHAR(100) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('ADMIN','MANAGER','AGENT') NOT NULL,
  specialization VARCHAR(100),
  skills TEXT
);

CREATE TABLE IF NOT EXISTS projects (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(150) NOT NULL,
  client_name VARCHAR(150) NOT NULL,
  description TEXT,
  manager_id VARCHAR(10) NOT NULL,
  deadline DATE NOT NULL,
  FOREIGN KEY (manager_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS tasks (
  id INT AUTO_INCREMENT PRIMARY KEY,
  project_id INT NOT NULL,
  title VARCHAR(150) NOT NULL,
  description TEXT,
  assignee_id VARCHAR(10) NOT NULL,
  deadline DATE NOT NULL,
  estimated_hours FLOAT NOT NULL,
  FOREIGN KEY (project_id) REFERENCES projects(id),
  FOREIGN KEY (assignee_id) REFERENCES users(id)
);
