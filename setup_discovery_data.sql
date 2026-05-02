USE discovery_service;

-- ========================================
-- BIG SEED FOR TOPOLOGY (Switch → RPi → HGW)
-- Works with TopologyService + parse_piserver()
-- ========================================

SET FOREIGN_KEY_CHECKS = 0;

TRUNCATE TABLE device_errors;
TRUNCATE TABLE piserver_snapshots;
TRUNCATE TABLE switch_mac_entries;
TRUNCATE TABLE hgw_facts;
TRUNCATE TABLE rpi_facts;
TRUNCATE TABLE switch_facts;
TRUNCATE TABLE discovery_runs;
TRUNCATE TABLE rpi_credential_overrides;
TRUNCATE TABLE hgws;
TRUNCATE TABLE rpis;
TRUNCATE TABLE switches;

SET FOREIGN_KEY_CHECKS = 1;

SET @now := NOW();

-- ========================================
-- RUNS
-- ========================================
INSERT INTO discovery_runs
(id, started_at, finished_at, status, triggered_by, message,
 switches_ok, switches_err, rpis_ok, rpis_err, hgws_ok, hgws_err)
VALUES
(1, @now - INTERVAL 2 HOUR,  @now - INTERVAL 110 MINUTE, 'done',    'superadmin', 'Big topology seed', 6, 0, 43, 2, 5, 1),
(2, @now - INTERVAL 45 MINUTE, @now - INTERVAL 40 MINUTE, 'partial','scheduler',  'Partial topology seed', 5, 1, 28, 17, 4, 2),
(3, @now - INTERVAL 10 MINUTE, NULL, 'running', 'admin', NULL, 0, 0, 0, 0, 0, 0);

-- ========================================
-- SWITCHES
-- ========================================
INSERT INTO switches
(id, name, ip, telnet_port, telnet_user, telnet_pass, enabled, created_at, last_seen,
 mac_address, firmware_version, uptime, serial_number, model)
VALUES
(1, 'Core Switch',         '192.168.1.10', 60000, 'admin', 'password', 1, @now, @now,
 '00:11:22:33:44:10', 'v12.4(5)MD', '12 weeks', 'FTX-CORE-001', 'Catalyst 2960X'),
(2, 'Access Switch A',     '192.168.1.11', 60000, 'admin', 'password', 1, @now, @now,
 '00:11:22:33:44:11', 'v12.4(5)MD', '8 weeks',  'FTX-ACC-001',  'Catalyst 2960X'),
(3, 'Access Switch B',     '192.168.1.12', 60000, 'admin', 'password', 1, @now, @now,
 '00:11:22:33:44:12', 'v12.4(5)MD', '7 weeks',  'FTX-ACC-002',  'Catalyst 2960X'),
(4, 'Access Switch C',     '192.168.1.13', 60000, 'admin', 'password', 1, @now, @now,
 '00:11:22:33:44:13', 'v12.4(5)MD', '6 weeks',  'FTX-ACC-003',  'Catalyst 2960X'),
(5, 'Access Switch D',     '192.168.1.14', 60000, 'admin', 'password', 1, @now, @now,
 '00:11:22:33:44:14', 'v12.4(5)MD', '5 weeks',  'FTX-ACC-004',  'Catalyst 2960X'),
(6, 'Distribution Switch', '192.168.1.20', 60000, 'admin', 'password', 0, @now, NULL,
 NULL, NULL, NULL, NULL, NULL);

-- ========================================
-- SWITCH FACTS (enrichissement)
-- ========================================
INSERT INTO switch_facts
(id, run_id, switch_ip, collected_at, mac_address, ip_address,
 firmware_version, loader_version, uptime, serial_number, model,
 default_gateway, cpu_5s, cpu_60s, cpu_300s, mem_free_kb, mem_alloc_kb,
 raw_show_info, raw_show_cpu, raw_show_mac)
VALUES
(1, 1, '192.168.1.10', @now - INTERVAL 2 HOUR, '00:11:22:33:44:10', '192.168.1.10',
 'v12.4(5)MD', 'C2960X-UNIVERSALK9-M', '12 weeks', 'FTX-CORE-001', 'WS-C2960X-24TS-L',
 '192.168.1.1', '5%', '4%', '3%', 300000, 500000, '...', '...', '...'),
(2, 1, '192.168.1.11', @now - INTERVAL 2 HOUR, '00:11:22:33:44:11', '192.168.1.11',
 'v12.4(5)MD', 'C2960X-UNIVERSALK9-M', '8 weeks', 'FTX-ACC-001', 'WS-C2960X-24TS-L',
 '192.168.1.1', '7%', '6%', '4%', 240000, 480000, '...', '...', '...'),
(3, 1, '192.168.1.12', @now - INTERVAL 2 HOUR, '00:11:22:33:44:12', '192.168.1.12',
 'v12.4(5)MD', 'C2960X-UNIVERSALK9-M', '7 weeks', 'FTX-ACC-002', 'WS-C2960X-24TS-L',
 '192.168.1.1', '9%', '7%', '5%', 220000, 480000, '...', '...', '...'),
(4, 1, '192.168.1.13', @now - INTERVAL 2 HOUR, '00:11:22:33:44:13', '192.168.1.13',
 'v12.4(5)MD', 'C2960X-UNIVERSALK9-M', '6 weeks', 'FTX-ACC-003', 'WS-C2960X-24TS-L',
 '192.168.1.1', '12%','10%','7%', 180000, 480000, '...', '...', '...'),
(5, 1, '192.168.1.14', @now - INTERVAL 2 HOUR, '00:11:22:33:44:14', '192.168.1.14',
 'v12.4(5)MD', 'C2960X-UNIVERSALK9-M', '5 weeks', 'FTX-ACC-004', 'WS-C2960X-24TS-L',
 '192.168.1.1', '6%', '5%', '4%', 260000, 480000, '...', '...', '...');

-- ========================================
-- HGWs (6 gateways)
-- ========================================
INSERT INTO hgws
(id, ip, hgw_type, via_rpi_ip, last_seen, manufacturer, model_name,
 serial_number, software_version, hardware_version, external_ip,
 uptime_seconds, mem_free_kb, mem_total_kb, created_at, updated_at)
VALUES
(1, '192.168.101.1', 'Sagemcom',    '192.168.1.101', @now, 'Sagemcom',    'F@ST 5360', 'SG101', 'V5.4.0', 'HW:1.0', '82.10.10.101', 864000, 200000, 500000, @now, @now),
(2, '192.168.102.1', 'Technicolor', '192.168.1.109', @now, 'Technicolor', 'TG789vac',  'TC102', 'V16.3.0','HW:2.0', '82.10.10.102', 432000, 120000, 260000, @now, @now),
(3, '192.168.103.1', 'Sagemcom',    '192.168.1.117', @now, 'Sagemcom',    'F@ST 5260', 'SG103', 'V4.2.0', 'HW:1.5', '82.10.10.103', 222000,  90000, 180000, @now, @now),
(4, '192.168.104.1', 'Technicolor', '192.168.1.125', @now, 'Technicolor', 'TG589vn',   'TC104', 'V15.4.0','HW:1.8', '82.10.10.104', 999999, 300000, 800000, @now, @now),
(5, '192.168.105.1', 'Sagemcom',    '192.168.1.133', @now, 'Sagemcom',    'F@ST 5360', 'SG105', 'V5.4.0', 'HW:1.0', '82.10.10.105', 111111, 450000,1000000, @now, @now),
(6, '192.168.106.1', 'Sagemcom',    '192.168.1.141', @now, 'Sagemcom',    'F@ST 5360', 'SG106', 'V5.4.0', 'HW:1.0', '82.10.10.106', 222222, 300000, 900000, @now, @now);

-- ========================================
-- RPIs (45)
-- 101-110 -> switch 192.168.1.11
-- 111-120 -> switch 192.168.1.12
-- 121-130 -> switch 192.168.1.13
-- 131-140 -> switch 192.168.1.14
-- 141-145 -> unassigned (no mac entry)
-- HGW sharing via rpi_facts.hgw_ip (many RPIs per HGW)
-- ========================================
INSERT INTO rpis
(id, mac, ip_mgmt, label, switch_ip, switch_port, hgw_ip, last_seen,
 last_ssh_success, last_ssh_error, created_at, updated_at)
VALUES
-- sw11
(1,  'b8:27:eb:12:34:65', '192.168.1.101', 'RPI-101', '192.168.1.11', 'Fa0/1',  '192.168.101.1', @now, 1, NULL, @now, @now),
(2,  'b8:27:eb:12:34:66', '192.168.1.102', 'RPI-102', '192.168.1.11', 'Fa0/2',  '192.168.101.1', @now, 1, NULL, @now, @now),
(3,  'b8:27:eb:12:34:67', '192.168.1.103', 'RPI-103', '192.168.1.11', 'Fa0/3',  '192.168.101.1', @now, 1, NULL, @now, @now),
(4,  'b8:27:eb:12:34:68', '192.168.1.104', 'RPI-104', '192.168.1.11', 'Fa0/4',  '192.168.101.1', @now, 1, NULL, @now, @now),
(5,  'b8:27:eb:12:34:69', '192.168.1.105', 'RPI-105', '192.168.1.11', 'Fa0/5',  '192.168.101.1', @now, 1, NULL, @now, @now),
(6,  'b8:27:eb:12:34:6a', '192.168.1.106', 'RPI-106', '192.168.1.11', 'Fa0/6',  '192.168.101.1', @now, 1, NULL, @now, @now),
(7,  'b8:27:eb:12:34:6b', '192.168.1.107', 'RPI-107', '192.168.1.11', 'Fa0/7',  '192.168.101.1', @now, 1, NULL, @now, @now),
(8,  'b8:27:eb:12:34:6c', '192.168.1.108', 'RPI-108', '192.168.1.11', 'Fa0/8',  '192.168.101.1', @now, 1, NULL, @now, @now),
(9,  'b8:27:eb:12:34:6d', '192.168.1.109', 'RPI-109', '192.168.1.11', 'Fa0/9',  '192.168.102.1', @now, 1, NULL, @now, @now),
(10, 'b8:27:eb:12:34:6e', '192.168.1.110', 'RPI-110', '192.168.1.11', 'Fa0/10', '192.168.102.1', @now, 1, NULL, @now, @now),

-- sw12
(11, 'b8:27:eb:12:34:6f', '192.168.1.111', 'RPI-111', '192.168.1.12', 'Fa0/1',  '192.168.102.1', @now, 1, NULL, @now, @now),
(12, 'b8:27:eb:12:34:70', '192.168.1.112', 'RPI-112', '192.168.1.12', 'Fa0/2',  '192.168.102.1', @now, 0, 'SSH auth failed', @now, @now),
(13, 'b8:27:eb:12:34:71', '192.168.1.113', 'RPI-113', '192.168.1.12', 'Fa0/3',  '192.168.102.1', @now, 1, NULL, @now, @now),
(14, 'b8:27:eb:12:34:72', '192.168.1.114', 'RPI-114', '192.168.1.12', 'Fa0/4',  '192.168.102.1', @now, 1, NULL, @now, @now),
(15, 'b8:27:eb:12:34:73', '192.168.1.115', 'RPI-115', '192.168.1.12', 'Fa0/5',  '192.168.102.1', @now, 1, NULL, @now, @now),
(16, 'b8:27:eb:12:34:74', '192.168.1.116', 'RPI-116', '192.168.1.12', 'Fa0/6',  '192.168.102.1', @now, 1, NULL, @now, @now),
(17, 'b8:27:eb:12:34:75', '192.168.1.117', 'RPI-117', '192.168.1.12', 'Fa0/7',  '192.168.103.1', @now, 1, NULL, @now, @now),
(18, 'b8:27:eb:12:34:76', '192.168.1.118', 'RPI-118', '192.168.1.12', 'Fa0/8',  '192.168.103.1', @now, 1, NULL, @now, @now),
(19, 'b8:27:eb:12:34:77', '192.168.1.119', 'RPI-119', '192.168.1.12', 'Fa0/9',  '192.168.103.1', @now, 1, NULL, @now, @now),
(20, 'b8:27:eb:12:34:78', '192.168.1.120', 'RPI-120', '192.168.1.12', 'Fa0/10', '192.168.103.1', @now, 1, NULL, @now, @now),

-- sw13
(21, 'b8:27:eb:12:34:79', '192.168.1.121', 'RPI-121', '192.168.1.13', 'Fa0/1',  '192.168.103.1', @now, 1, NULL, @now, @now),
(22, 'b8:27:eb:12:34:7a', '192.168.1.122', 'RPI-122', '192.168.1.13', 'Fa0/2',  '192.168.103.1', @now, 1, NULL, @now, @now),
(23, 'b8:27:eb:12:34:7b', '192.168.1.123', 'RPI-123', '192.168.1.13', 'Fa0/3',  '192.168.103.1', @now, 1, NULL, @now, @now),
(24, 'b8:27:eb:12:34:7c', '192.168.1.124', 'RPI-124', '192.168.1.13', 'Fa0/4',  '192.168.103.1', @now, 1, NULL, @now, @now),
(25, 'b8:27:eb:12:34:7d', '192.168.1.125', 'RPI-125', '192.168.1.13', 'Fa0/5',  '192.168.104.1', @now, 1, NULL, @now, @now),
(26, 'b8:27:eb:12:34:7e', '192.168.1.126', 'RPI-126', '192.168.1.13', 'Fa0/6',  '192.168.104.1', @now, 1, NULL, @now, @now),
(27, 'b8:27:eb:12:34:7f', '192.168.1.127', 'RPI-127', '192.168.1.13', 'Fa0/7',  '192.168.104.1', @now, 1, NULL, @now, @now),
(28, 'b8:27:eb:12:34:80', '192.168.1.128', 'RPI-128', '192.168.1.13', 'Fa0/8',  '192.168.104.1', @now, 1, NULL, @now, @now),
(29, 'b8:27:eb:12:34:81', '192.168.1.129', 'RPI-129', '192.168.1.13', 'Fa0/9',  '192.168.104.1', @now, 1, NULL, @now, @now),
(30, 'b8:27:eb:12:34:82', '192.168.1.130', 'RPI-130', '192.168.1.13', 'Fa0/10', '192.168.104.1', @now, 1, NULL, @now, @now),

-- sw14
(31, 'b8:27:eb:12:34:83', '192.168.1.131', 'RPI-131', '192.168.1.14', 'Fa0/1',  '192.168.104.1', @now, 1, NULL, @now, @now),
(32, 'b8:27:eb:12:34:84', '192.168.1.132', 'RPI-132', '192.168.1.14', 'Fa0/2',  '192.168.104.1', @now, 1, NULL, @now, @now),
(33, 'b8:27:eb:12:34:85', '192.168.1.133', 'RPI-133', '192.168.1.14', 'Fa0/3',  '192.168.105.1', @now, 1, NULL, @now, @now),
(34, 'b8:27:eb:12:34:86', '192.168.1.134', 'RPI-134', '192.168.1.14', 'Fa0/4',  '192.168.105.1', @now, 1, NULL, @now, @now),
(35, 'b8:27:eb:12:34:87', '192.168.1.135', 'RPI-135', '192.168.1.14', 'Fa0/5',  '192.168.105.1', @now, 1, NULL, @now, @now),
(36, 'b8:27:eb:12:34:88', '192.168.1.136', 'RPI-136', '192.168.1.14', 'Fa0/6',  '192.168.105.1', @now, 1, NULL, @now, @now),
(37, 'b8:27:eb:12:34:89', '192.168.1.137', 'RPI-137', '192.168.1.14', 'Fa0/7',  '192.168.105.1', @now, 1, NULL, @now, @now),
(38, 'b8:27:eb:12:34:8a', '192.168.1.138', 'RPI-138', '192.168.1.14', 'Fa0/8',  '192.168.105.1', @now, 0, 'Connection timeout', @now, @now),
(39, 'b8:27:eb:12:34:8b', '192.168.1.139', 'RPI-139', '192.168.1.14', 'Fa0/9',  '192.168.105.1', @now, 1, NULL, @now, @now),
(40, 'b8:27:eb:12:34:8c', '192.168.1.140', 'RPI-140', '192.168.1.14', 'Fa0/10', '192.168.105.1', @now, 1, NULL, @now, @now),

-- unassigned (no switch_ip + will have no mac entries)
(41, 'b8:27:eb:12:34:8d', '192.168.1.141', 'RPI-141', NULL, NULL, '192.168.106.1', @now, 1, NULL, @now, @now),
(42, 'b8:27:eb:12:34:8e', '192.168.1.142', 'RPI-142', NULL, NULL, '192.168.106.1', @now, 1, NULL, @now, @now),
(43, 'b8:27:eb:12:34:8f', '192.168.1.143', 'RPI-143', NULL, NULL, '192.168.106.1', @now, 1, NULL, @now, @now),
(44, 'b8:27:eb:12:34:90', '192.168.1.144', 'RPI-144', NULL, NULL, '192.168.106.1', @now, 1, NULL, @now, @now),
(45, 'b8:27:eb:12:34:91', '192.168.1.145', 'RPI-145', NULL, NULL, '192.168.106.1', @now, 1, NULL, @now, @now);

-- ========================================
-- PISERVER SNAPSHOTS
-- IMPORTANT: content généré automatiquement depuis rpis (zéro problème de format)
-- ========================================
SET SESSION group_concat_max_len = 1000000;

INSERT INTO piserver_snapshots (id, run_id, collected_at, content) VALUES
(1, 1, @now - INTERVAL 2 HOUR, ''),
(2, 2, @now - INTERVAL 45 MINUTE, ''),
(3, 3, @now - INTERVAL 10 MINUTE, '');

UPDATE piserver_snapshots
SET content = CONCAT(
  '##AUTO_SEED\n',
  (SELECT GROUP_CONCAT(
     CONCAT('#', label, '\n', 'dhcp-host=', UPPER(mac), ',set:piserver,', ip_mgmt)
     ORDER BY ip_mgmt
     SEPARATOR '\n'
   ) FROM rpis)
)
WHERE run_id IN (1,2,3);

-- ========================================
-- RPI FACTS (RUN 1) : indispensables pour HGW (hgw_ip)
-- (on met des valeurs simples + placeholders)
-- ========================================
INSERT INTO rpi_facts
(id, run_id, rpi_mac, rpi_ip_mgmt, collected_at, hostname, os_name,
 os_version, os_pretty, model, kernel, lan_iface, lan_ip, hgw_ip,
 all_ips, temp_celsius, mem_total_mb, mem_used_mb, mem_free_mb,
 disk_total_gb, disk_used_gb, disk_used_pct, running_scripts,
 running_python, docker_available, docker_containers, usb_devices,
 raw_ifconfig, raw_ps)
SELECT
  id,
  1 AS run_id,
  UPPER(mac) AS rpi_mac,
  ip_mgmt AS rpi_ip_mgmt,
  @now - INTERVAL 2 HOUR AS collected_at,
  LOWER(REPLACE(label,'-','_')) AS hostname,
  'Raspbian GNU/Linux' AS os_name,
  '11' AS os_version,
  'Raspbian GNU/Linux 11 (bullseye)' AS os_pretty,
  'Raspberry Pi 4 Model B' AS model,
  '5.10.63-v7l+' AS kernel,
  'eth0' AS lan_iface,
  ip_mgmt AS lan_ip,
  hgw_ip AS hgw_ip,
  CONCAT('["', ip_mgmt, '"]') AS all_ips,
  43.5 AS temp_celsius,
  4096 AS mem_total_mb,
  900 AS mem_used_mb,
  3196 AS mem_free_mb,
  '32.0' AS disk_total_gb,
  '12.0' AS disk_used_gb,
  '37.5%' AS disk_used_pct,
  '["ssh","dhcpcd"]' AS running_scripts,
  '["/usr/bin/python3"]' AS running_python,
  1 AS docker_available,
  '[]' AS docker_containers,
  '[]' AS usb_devices,
  'ifconfig_output...' AS raw_ifconfig,
  'ps_output...' AS raw_ps
FROM rpis;

-- ========================================
-- HGW FACTS (RUN 1)
-- ========================================
INSERT INTO hgw_facts
(id, run_id, hgw_ip, via_rpi_ip, collected_at, manufacturer, model_name,
 serial_number, software_version, hardware_version, external_ip,
 uptime_seconds, mem_free_kb, mem_total_kb, base_mac, country,
 device_status, raw_deviceinfo, ssh_error)
VALUES
(1, 1, '192.168.101.1', '192.168.1.101', @now - INTERVAL 2 HOUR, 'Sagemcom',    'F@ST 5360', 'SG101', 'V5.4.0',  'HW:1.0', '82.10.10.101', 864000, 200000, 500000, '00:11:22:33:44:66', 'FR', 'OK', 'deviceinfo...', NULL),
(2, 1, '192.168.102.1', '192.168.1.109', @now - INTERVAL 2 HOUR, 'Technicolor', 'TG789vac',  'TC102', 'V16.3.0', 'HW:2.0', '82.10.10.102', 432000, 120000, 260000, '00:11:22:33:44:67', 'FR', 'OK', 'deviceinfo...', NULL),
(3, 1, '192.168.103.1', '192.168.1.117', @now - INTERVAL 2 HOUR, 'Sagemcom',    'F@ST 5260', 'SG103', 'V4.2.0',  'HW:1.5', '82.10.10.103', 222000,  90000, 180000, '00:11:22:33:44:68', 'FR', 'OK', 'deviceinfo...', NULL),
(4, 1, '192.168.104.1', '192.168.1.125', @now - INTERVAL 2 HOUR, 'Technicolor', 'TG589vn',   'TC104', 'V15.4.0', 'HW:1.8', '82.10.10.104', 999999, 300000, 800000, '00:11:22:33:44:69', 'FR', 'OK', 'deviceinfo...', NULL),
(5, 1, '192.168.105.1', '192.168.1.133', @now - INTERVAL 2 HOUR, 'Sagemcom',    'F@ST 5360', 'SG105', 'V5.4.0',  'HW:1.0', '82.10.10.105', 111111, 450000,1000000, '00:11:22:33:44:6A', 'FR', 'OK', 'deviceinfo...', NULL),
(6, 1, '192.168.106.1', '192.168.1.141', @now - INTERVAL 2 HOUR, 'Sagemcom',    'F@ST 5360', 'SG106', 'V5.4.0',  'HW:1.0', '82.10.10.106', 222222, 300000, 900000, '00:11:22:33:44:6B', 'FR', 'OK', 'deviceinfo...', NULL);

-- ========================================
-- SWITCH MAC ENTRIES
-- RUN 1: 40 assigned (101-140)
-- RUN 2: subset (partial)
-- RUN 3: subset (running)
-- ========================================

-- RUN 1
INSERT INTO switch_mac_entries (id, run_id, switch_ip, vid, mac, entry_type, port, raw_line) VALUES
-- sw11 (101-110)
(1,  1, '192.168.1.11', 1, 'b8:27:eb:12:34:65', 'Dynamic', 'Fa0/1',  '...'),
(2,  1, '192.168.1.11', 1, 'b8:27:eb:12:34:66', 'Dynamic', 'Fa0/2',  '...'),
(3,  1, '192.168.1.11', 1, 'b8:27:eb:12:34:67', 'Dynamic', 'Fa0/3',  '...'),
(4,  1, '192.168.1.11', 1, 'b8:27:eb:12:34:68', 'Dynamic', 'Fa0/4',  '...'),
(5,  1, '192.168.1.11', 1, 'b8:27:eb:12:34:69', 'Dynamic', 'Fa0/5',  '...'),
(6,  1, '192.168.1.11', 1, 'b8:27:eb:12:34:6a', 'Dynamic', 'Fa0/6',  '...'),
(7,  1, '192.168.1.11', 1, 'b8:27:eb:12:34:6b', 'Dynamic', 'Fa0/7',  '...'),
(8,  1, '192.168.1.11', 1, 'b8:27:eb:12:34:6c', 'Dynamic', 'Fa0/8',  '...'),
(9,  1, '192.168.1.11', 1, 'b8:27:eb:12:34:6d', 'Dynamic', 'Fa0/9',  '...'),
(10, 1, '192.168.1.11', 1, 'b8:27:eb:12:34:6e', 'Dynamic', 'Fa0/10', '...'),

-- sw12 (111-120)
(11, 1, '192.168.1.12', 1, 'b8:27:eb:12:34:6f', 'Dynamic', 'Fa0/1',  '...'),
(12, 1, '192.168.1.12', 1, 'b8:27:eb:12:34:70', 'Dynamic', 'Fa0/2',  '...'),
(13, 1, '192.168.1.12', 1, 'b8:27:eb:12:34:71', 'Dynamic', 'Fa0/3',  '...'),
(14, 1, '192.168.1.12', 1, 'b8:27:eb:12:34:72', 'Dynamic', 'Fa0/4',  '...'),
(15, 1, '192.168.1.12', 1, 'b8:27:eb:12:34:73', 'Dynamic', 'Fa0/5',  '...'),
(16, 1, '192.168.1.12', 1, 'b8:27:eb:12:34:74', 'Dynamic', 'Fa0/6',  '...'),
(17, 1, '192.168.1.12', 1, 'b8:27:eb:12:34:75', 'Dynamic', 'Fa0/7',  '...'),
(18, 1, '192.168.1.12', 1, 'b8:27:eb:12:34:76', 'Dynamic', 'Fa0/8',  '...'),
(19, 1, '192.168.1.12', 1, 'b8:27:eb:12:34:77', 'Dynamic', 'Fa0/9',  '...'),
(20, 1, '192.168.1.12', 1, 'b8:27:eb:12:34:78', 'Dynamic', 'Fa0/10', '...'),

-- sw13 (121-130)
(21, 1, '192.168.1.13', 1, 'b8:27:eb:12:34:79', 'Dynamic', 'Fa0/1',  '...'),
(22, 1, '192.168.1.13', 1, 'b8:27:eb:12:34:7a', 'Dynamic', 'Fa0/2',  '...'),
(23, 1, '192.168.1.13', 1, 'b8:27:eb:12:34:7b', 'Dynamic', 'Fa0/3',  '...'),
(24, 1, '192.168.1.13', 1, 'b8:27:eb:12:34:7c', 'Dynamic', 'Fa0/4',  '...'),
(25, 1, '192.168.1.13', 1, 'b8:27:eb:12:34:7d', 'Dynamic', 'Fa0/5',  '...'),
(26, 1, '192.168.1.13', 1, 'b8:27:eb:12:34:7e', 'Dynamic', 'Fa0/6',  '...'),
(27, 1, '192.168.1.13', 1, 'b8:27:eb:12:34:7f', 'Dynamic', 'Fa0/7',  '...'),
(28, 1, '192.168.1.13', 1, 'b8:27:eb:12:34:80', 'Dynamic', 'Fa0/8',  '...'),
(29, 1, '192.168.1.13', 1, 'b8:27:eb:12:34:81', 'Dynamic', 'Fa0/9',  '...'),
(30, 1, '192.168.1.13', 1, 'b8:27:eb:12:34:82', 'Dynamic', 'Fa0/10', '...'),

-- sw14 (131-140)
(31, 1, '192.168.1.14', 1, 'b8:27:eb:12:34:83', 'Dynamic', 'Fa0/1',  '...'),
(32, 1, '192.168.1.14', 1, 'b8:27:eb:12:34:84', 'Dynamic', 'Fa0/2',  '...'),
(33, 1, '192.168.1.14', 1, 'b8:27:eb:12:34:85', 'Dynamic', 'Fa0/3',  '...'),
(34, 1, '192.168.1.14', 1, 'b8:27:eb:12:34:86', 'Dynamic', 'Fa0/4',  '...'),
(35, 1, '192.168.1.14', 1, 'b8:27:eb:12:34:87', 'Dynamic', 'Fa0/5',  '...'),
(36, 1, '192.168.1.14', 1, 'b8:27:eb:12:34:88', 'Dynamic', 'Fa0/6',  '...'),
(37, 1, '192.168.1.14', 1, 'b8:27:eb:12:34:89', 'Dynamic', 'Fa0/7',  '...'),
(38, 1, '192.168.1.14', 1, 'b8:27:eb:12:34:8a', 'Dynamic', 'Fa0/8',  '...'),
(39, 1, '192.168.1.14', 1, 'b8:27:eb:12:34:8b', 'Dynamic', 'Fa0/9',  '...'),
(40, 1, '192.168.1.14', 1, 'b8:27:eb:12:34:8c', 'Dynamic', 'Fa0/10', '...');

-- RUN 2 (partial subset)
INSERT INTO switch_mac_entries (id, run_id, switch_ip, vid, mac, entry_type, port, raw_line) VALUES
(101, 2, '192.168.1.11', 1, 'b8:27:eb:12:34:65', 'Dynamic', 'Fa0/1', '...'),
(102, 2, '192.168.1.11', 1, 'b8:27:eb:12:34:66', 'Dynamic', 'Fa0/2', '...'),
(103, 2, '192.168.1.11', 1, 'b8:27:eb:12:34:67', 'Dynamic', 'Fa0/3', '...'),
(104, 2, '192.168.1.12', 1, 'b8:27:eb:12:34:6f', 'Dynamic', 'Fa0/1', '...'),
(105, 2, '192.168.1.12', 1, 'b8:27:eb:12:34:71', 'Dynamic', 'Fa0/3', '...'),
(106, 2, '192.168.1.13', 1, 'b8:27:eb:12:34:7d', 'Dynamic', 'Fa0/5', '...'),
(107, 2, '192.168.1.14', 1, 'b8:27:eb:12:34:83', 'Dynamic', 'Fa0/1', '...');

-- RUN 3 (running subset)
INSERT INTO switch_mac_entries (id, run_id, switch_ip, vid, mac, entry_type, port, raw_line) VALUES
(201, 3, '192.168.1.11', 1, 'b8:27:eb:12:34:65', 'Dynamic', 'Fa0/1', '...'),
(202, 3, '192.168.1.11', 1, 'b8:27:eb:12:34:66', 'Dynamic', 'Fa0/2', '...'),
(203, 3, '192.168.1.12', 1, 'b8:27:eb:12:34:6f', 'Dynamic', 'Fa0/1', '...'),
(204, 3, '192.168.1.14', 1, 'b8:27:eb:12:34:83', 'Dynamic', 'Fa0/1', '...');

-- ========================================
-- DEVICE ERRORS (RUN 1) -> pour "FAILED"
-- TopologyService:
-- - RPi ssh_success = false si device_errors contient device_type='rpi'
-- - HGW ssh_success = false si device_errors contient device_type='hgw'
-- - Switch error via device_type='switch'
-- ========================================
INSERT INTO device_errors (id, run_id, device_type, device_ip, stage, error, created_at) VALUES
(1, 1, 'rpi',    '192.168.1.112', 'ssh',        'SSH authentication failed', @now - INTERVAL 105 MINUTE),
(2, 1, 'rpi',    '192.168.1.138', 'ssh',        'Connection timeout',        @now - INTERVAL 105 MINUTE),
(3, 1, 'hgw',    '192.168.103.1', 'connection', 'HGW unreachable via RPi',   @now - INTERVAL 105 MINUTE),
(4, 1, 'switch', '192.168.1.13',  'connection', 'Telnet timeout',            @now - INTERVAL 105 MINUTE);

-- ========================================
-- Credential override (exemple)
-- ========================================
INSERT INTO rpi_credential_overrides
(id, rpi_ip_mgmt, ssh_user, ssh_pass, submitted_by, created_at, updated_at)
VALUES
(1, '192.168.1.112', 'pi', 'newpassword123', 'admin', @now - INTERVAL 1 DAY, @now - INTERVAL 1 DAY);

-- ========================================
-- CHECKS
-- ========================================
SELECT 'switches' AS tbl, COUNT(*) AS cnt FROM switches
UNION ALL SELECT 'rpis', COUNT(*) FROM rpis
UNION ALL SELECT 'hgws', COUNT(*) FROM hgws
UNION ALL SELECT 'runs', COUNT(*) FROM discovery_runs
UNION ALL SELECT 'snapshots', COUNT(*) FROM piserver_snapshots
UNION ALL SELECT 'mac_entries', COUNT(*) FROM switch_mac_entries
UNION ALL SELECT 'rpi_facts', COUNT(*) FROM rpi_facts
UNION ALL SELECT 'hgw_facts', COUNT(*) FROM hgw_facts
UNION ALL SELECT 'errors', COUNT(*) FROM device_errors;