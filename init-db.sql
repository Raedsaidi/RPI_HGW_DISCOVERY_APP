-- Création des bases de données (Utilisez seulement -- pour les commentaires)
CREATE DATABASE IF NOT EXISTS auth_service;
CREATE DATABASE IF NOT EXISTS discovery_service;

-- Création de l'utilisateur
CREATE USER IF NOT EXISTS 'app_user'@'%' IDENTIFIED BY 'app_password';
GRANT ALL PRIVILEGES ON auth_service.* TO 'app_user'@'%';
GRANT ALL PRIVILEGES ON discovery_service.* TO 'app_user'@'%';

FLUSH PRIVILEGES;