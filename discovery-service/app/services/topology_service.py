# app/services/topology_service.py

import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.repositories.discovery_repo import DiscoveryRepository
from app.repositories.switch_repo import SwitchRepository
from app.repositories.rpi_repo import RpiRepository
from app.repositories.hgw_repo import HgwRepository
from app.parsers.piserver_parser import parse_piserver
from app.clients.user_client import UserServiceClient
from app.schemas.user_schema import UserRole

logger = logging.getLogger(__name__)

FULL_ACCESS_ROLES = {UserRole.SUPER_ADMIN.value, UserRole.ADMIN.value}


class TopologyService:
    """Build topology tree: Switch → RPi → HGW."""

    def __init__(self, db: Session, user_client: UserServiceClient):
        self.db = db
        self.user_client = user_client
        self.discovery_repo = DiscoveryRepository(db)
        self.switch_repo = SwitchRepository(db)
        self.rpi_repo = RpiRepository(db)
        self.hgw_repo = HgwRepository(db)

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC HELPERS
    # ─────────────────────────────────────────────────────────────────────

    def get_latest_run_id(self) -> Optional[int]:
        runs = self.discovery_repo.list_runs(skip=0, limit=1)
        return runs[0].id if runs else None

    def get_user_hgw_identifiers(self, username: str) -> list[str]:
        """
        Retourne les hgw_identifiers assignés à un user (via User Service).
        Identifiers existants: serial_number ou ip (legacy).
        """
        return self.user_client.get_user_hgw_identifiers(username)

    # ─────────────────────────────────────────────────────────────────────
    # FULL TOPOLOGY
    # ─────────────────────────────────────────────────────────────────────

    def get_topology_for_run(self, run_id: int) -> dict:
        ctx = self._build_context(run_id)
        return self._assemble_topology(run_id, ctx)

    # ─────────────────────────────────────────────────────────────────────
    # FILTER BY SWITCH
    # ─────────────────────────────────────────────────────────────────────

    def get_topology_for_switch(self, run_id: int, switch_ip: str) -> dict:
        full = self.get_topology_for_run(run_id)

        matched = [sw for sw in full["switches"] if sw["ip"] == switch_ip]
        if not matched:
            return {
                **{k: full[k] for k in ("run_id", "run_status", "run_started_at", "run_finished_at")},
                "switches": [],
                "unassigned_rpis": [],
                "total_rpis": 0,
                "total_assigned": 0,
                "errors": [],
                "filter": {"type": "switch", "switch_ip": switch_ip},
            }

        sw = matched[0]
        switch_rpi_ips = {rpi["ip_mgmt"] for rpi in sw.get("rpis", [])}

        # NEW: inclure aussi erreurs HGW (keyed by instance_key)
        switch_hgw_keys = set()
        for rpi in sw.get("rpis", []):
            hgw = rpi.get("hgw")
            if hgw and hgw.get("instance_key"):
                switch_hgw_keys.add(hgw["instance_key"])

        filtered_errors = [
            e for e in full["errors"]
            if e["device_ip"] == switch_ip
            or e["device_ip"] in switch_rpi_ips
            or e["device_ip"] in switch_hgw_keys
        ]

        return {
            **{k: full[k] for k in ("run_id", "run_status", "run_started_at", "run_finished_at")},
            "switches": [sw],
            "unassigned_rpis": [],
            "total_rpis": len(sw.get("rpis", [])),
            "total_assigned": len(switch_rpi_ips),
            "errors": filtered_errors,
            "filter": {"type": "switch", "switch_ip": switch_ip},
        }

    # ─────────────────────────────────────────────────────────────────────
    # FILTER BY HGW IDENTIFIER
    # ─────────────────────────────────────────────────────────────────────

    def get_topology_for_hgw(self, run_id: int, hgw_identifier: str) -> dict:
        full = self.get_topology_for_run(run_id)
        return self._filter_by_hgw_identifiers(full, [hgw_identifier])

    def get_topology_for_user(self, run_id: int, username: str) -> dict:
        identifiers = self.get_user_hgw_identifiers(username)
        if not identifiers:
            full = self.get_topology_for_run(run_id)
            return {
                **{k: full[k] for k in ("run_id", "run_status", "run_started_at", "run_finished_at")},
                "switches": [],
                "unassigned_rpis": [],
                "total_rpis": 0,
                "total_assigned": 0,
                "errors": [],
                "filter": {"type": "user_hgw", "identifiers": []},
            }
        full = self.get_topology_for_run(run_id)
        result = self._filter_by_hgw_identifiers(full, identifiers)
        result["filter"]["type"] = "user_hgw"
        return result

    # ─────────────────────────────────────────────────────────────────────
    # MY-HGWS
    # ─────────────────────────────────────────────────────────────────────

    def get_my_hgws(self, run_id: int, username: str) -> list[dict]:
        identifiers = self.get_user_hgw_identifiers(username)
        if not identifiers:
            return []

        full = self.get_topology_for_run(run_id)
        seen: dict[str, dict] = {}

        for sw in full.get("switches", []):
            for rpi in sw.get("rpis", []):
                hgw = rpi.get("hgw")
                if not hgw:
                    continue

                hgw_ip = hgw.get("ip")
                serial = hgw.get("serial_number")
                instance_key = hgw.get("instance_key")

                # matching selon identifiers (legacy = serial ou IP)
                matched_id = None
                for ident in identifiers:
                    if (serial and ident == serial) or (hgw_ip and ident == hgw_ip):
                        matched_id = ident
                        break
                if not matched_id:
                    continue

                # NEW: ne plus dédupliquer par IP seule
                key = serial or instance_key or hgw_ip
                if key not in seen:
                    seen[key] = {
                        "hgw_identifier": matched_id,
                        "ip":             hgw_ip,
                        "serial_number":  serial,
                        "instance_key":   instance_key,
                        "model_name":     hgw.get("model_name"),
                        "manufacturer":   hgw.get("manufacturer"),
                        "external_ip":    hgw.get("external_ip"),
                        "ssh_success":    hgw.get("ssh_success"),
                        "network":        hgw.get("network"),
                    }

        return list(seen.values())

    # ─────────────────────────────────────────────────────────────────────
    # PRIVATE : FILTER BY HGW IDENTIFIERS
    # ─────────────────────────────────────────────────────────────────────

    def _filter_by_hgw_identifiers(self, full: dict, identifiers: list[str]) -> dict:
        """
        Identifiers = serial ou IP (legacy).
        Note: si identifier=IP (ex 192.168.1.1) et plusieurs sites partagent la même IP,
        alors ce filtre matchera plusieurs HGW (ce qui est logique).
        """
        id_set = set(identifiers)
        filtered_switches = []
        total_assigned = 0
        filtered_errors = []

        for sw in full.get("switches", []):
            matching_rpis = []
            for rpi in sw.get("rpis", []):
                hgw = rpi.get("hgw")
                if not hgw:
                    continue
                hgw_ip = hgw.get("ip", "")
                serial = hgw.get("serial_number", "")
                if hgw_ip in id_set or serial in id_set:
                    matching_rpis.append(rpi)

            if matching_rpis:
                filtered_switches.append({
                    **sw,
                    "rpis": matching_rpis,
                    "rpi_count": len(matching_rpis),
                })
                total_assigned += len(matching_rpis)

                rpi_ips = {r["ip_mgmt"] for r in matching_rpis}
                hgw_keys = {
                    r.get("hgw", {}).get("instance_key")
                    for r in matching_rpis
                    if r.get("hgw")
                }
                hgw_keys.discard(None)

                for e in full.get("errors", []):
                    if (
                        e["device_ip"] == sw["ip"]
                        or e["device_ip"] in rpi_ips
                        or e["device_ip"] in hgw_keys
                    ):
                        filtered_errors.append(e)

        return {
            **{k: full[k] for k in ("run_id", "run_status", "run_started_at", "run_finished_at")},
            "switches": filtered_switches,
            "unassigned_rpis": [],
            "total_rpis": total_assigned,
            "total_assigned": total_assigned,
            "errors": filtered_errors,
            "filter": {"type": "hgw", "identifiers": list(id_set)},
        }

    # ─────────────────────────────────────────────────────────────────────
    # PRIVATE : BUILD CONTEXT
    # ─────────────────────────────────────────────────────────────────────

    def _build_context(self, run_id: int) -> dict:
        from app.models.discovery_run import PiserverSnapshot

        snap = (
            self.db.query(PiserverSnapshot)
            .filter(PiserverSnapshot.run_id == run_id)
            .order_by(PiserverSnapshot.id.desc())
            .first()
        )
        piserver_content = snap.content if snap else ""
        rpi_entries = parse_piserver(piserver_content)

        piserver_mac_to_ip = {e.mac: e.ip_mgmt for e in rpi_entries}
        piserver_ip_to_mac = {e.ip_mgmt: e.mac for e in rpi_entries}
        piserver_ip_to_label = {e.ip_mgmt: e.label for e in rpi_entries}

        mac_entries = self.switch_repo.get_mac_entries_for_run(run_id)

        switch_rpi_map: dict[str, dict[str, str]] = {}
        for entry in mac_entries:
            mac_u = entry.mac.upper()
            if mac_u in piserver_mac_to_ip:
                rpi_ip = piserver_mac_to_ip[mac_u]
                if entry.switch_ip not in switch_rpi_map:
                    switch_rpi_map[entry.switch_ip] = {}
                switch_rpi_map[entry.switch_ip][rpi_ip] = entry.port

        rpi_facts = self.rpi_repo.get_facts_for_run(run_id)
        rpi_fact_map = {f.rpi_ip_mgmt: f for f in rpi_facts}

        hgw_facts = self.hgw_repo.get_facts_for_run(run_id)

        # Legacy maps (kept as fallback)
        hgw_fact_path_map: dict[str, object] = {}
        hgw_fact_ip_map: dict[str, object] = {}
        hgw_ip_counts: dict[str, int] = {}

        for fact in hgw_facts:
            if fact.hgw_ip:
                hgw_ip_counts[fact.hgw_ip] = hgw_ip_counts.get(fact.hgw_ip, 0) + 1

        for fact in hgw_facts:
            if fact.serial_number:
                key = f"serial:{fact.serial_number}"
                existing = hgw_fact_path_map.get(key)
                if not existing or (
                    fact.collected_at and existing.collected_at
                    and fact.collected_at > existing.collected_at
                ):
                    hgw_fact_path_map[key] = fact

            if fact.hgw_ip and fact.via_rpi_ip:
                path_key = f"{fact.hgw_ip}|{fact.via_rpi_ip}"
                existing = hgw_fact_path_map.get(path_key)
                if not existing or (
                    fact.collected_at and existing.collected_at
                    and fact.collected_at > existing.collected_at
                ):
                    hgw_fact_path_map[path_key] = fact

            if fact.hgw_ip and hgw_ip_counts.get(fact.hgw_ip, 0) == 1:
                existing_ip = hgw_fact_ip_map.get(fact.hgw_ip)
                if not existing_ip or (
                    fact.collected_at and existing_ip.collected_at
                    and fact.collected_at > existing_ip.collected_at
                ):
                    hgw_fact_ip_map[fact.hgw_ip] = fact

        # NEW: primary map by instance_key (gateway MAC or fallback switch|ip)
        hgw_fact_instance_map: dict[str, object] = {}
        for fact in hgw_facts:
            key = getattr(fact, "instance_key", None)
            if not key:
                continue
            existing = hgw_fact_instance_map.get(key)
            if not existing or (
                fact.collected_at and existing.collected_at
                and fact.collected_at > existing.collected_at
            ):
                hgw_fact_instance_map[key] = fact

        errors = self.discovery_repo.get_errors_for_run(run_id)

        # NOTE:
        # - rpi errors keyed by rpi_ip
        # - switch errors keyed by switch_ip
        # - hgw errors: in our new DiscoveryService we save device_ip = instance_key
        rpi_errors = {e.device_ip: e.error for e in errors if e.device_type == "rpi"}
        hgw_errors = {e.device_ip: e.error for e in errors if e.device_type == "hgw"}
        switch_errors = {e.device_ip: e.error for e in errors if e.device_type == "switch"}

        return dict(
            rpi_entries=rpi_entries,
            piserver_mac_to_ip=piserver_mac_to_ip,
            piserver_ip_to_mac=piserver_ip_to_mac,
            piserver_ip_to_label=piserver_ip_to_label,
            switch_rpi_map=switch_rpi_map,
            rpi_fact_map=rpi_fact_map,
            hgw_fact_path_map=hgw_fact_path_map,
            hgw_fact_ip_map=hgw_fact_ip_map,
            hgw_fact_instance_map=hgw_fact_instance_map,  # NEW
            rpi_errors=rpi_errors,
            hgw_errors=hgw_errors,
            switch_errors=switch_errors,
            errors=errors,
        )

    # ─────────────────────────────────────────────────────────────────────
    # PRIVATE : ASSEMBLE TOPOLOGY
    # ─────────────────────────────────────────────────────────────────────

    def _assemble_topology(self, run_id: int, ctx: dict) -> dict:
        (
            rpi_entries, piserver_ip_to_mac,
            piserver_ip_to_label, switch_rpi_map, rpi_fact_map,
            hgw_fact_path_map, hgw_fact_ip_map, hgw_fact_instance_map,
            rpi_errors, hgw_errors, switch_errors, errors,
        ) = (ctx[k] for k in (
            "rpi_entries", "piserver_ip_to_mac",
            "piserver_ip_to_label", "switch_rpi_map", "rpi_fact_map",
            "hgw_fact_path_map", "hgw_fact_ip_map", "hgw_fact_instance_map",
            "rpi_errors", "hgw_errors", "switch_errors", "errors",
        ))

        switches_configured = self.switch_repo.list_all()
        result_switches: list[dict] = []
        all_assigned_rpis: set[str] = set()

        for sw in switches_configured:
            sw_fact = self.switch_repo.get_last_fact(sw.ip)
            rpi_port_map = switch_rpi_map.get(sw.ip, {})

            rpis_on_switch = []
            for rpi_ip, port in sorted(rpi_port_map.items()):
                all_assigned_rpis.add(rpi_ip)
                rpi_fact = rpi_fact_map.get(rpi_ip)

                hgw_ip = rpi_fact.hgw_ip if rpi_fact else None
                hgw_fact = None
                instance_key = None

                if hgw_ip:
                    # instance_key priority:
                    # 1) gateway mac collected on the RPi
                    gw_mac = getattr(rpi_fact, "hgw_gateway_mac", None) if rpi_fact else None
                    if gw_mac:
                        instance_key = str(gw_mac).upper()
                    else:
                        # fallback must match DiscoveryService fallback
                        instance_key = f"{sw.ip}|{hgw_ip}"

                    # 1) Primary: match by instance_key
                    hgw_fact = hgw_fact_instance_map.get(instance_key)

                    # 2) Fallback legacy
                    if not hgw_fact:
                        hgw_fact = hgw_fact_path_map.get(f"{hgw_ip}|{rpi_ip}")
                        if not hgw_fact:
                            hgw_fact = hgw_fact_ip_map.get(hgw_ip)

                rpis_on_switch.append({
                    "ip_mgmt":          rpi_ip,
                    "mac":              piserver_ip_to_mac.get(rpi_ip),
                    "label":            piserver_ip_to_label.get(rpi_ip),
                    "switch_port":      port,
                    "hostname":         rpi_fact.hostname if rpi_fact else None,
                    "model":            rpi_fact.model if rpi_fact else None,
                    "os_pretty":        rpi_fact.os_pretty if rpi_fact else None,
                    "temp_celsius":     rpi_fact.temp_celsius if rpi_fact else None,
                    "mem_total_mb":     rpi_fact.mem_total_mb if rpi_fact else None,
                    "mem_used_mb":      rpi_fact.mem_used_mb if rpi_fact else None,
                    "disk_used_pct":    rpi_fact.disk_used_pct if rpi_fact else None,
                    "docker_available": rpi_fact.docker_available if rpi_fact else None,
                    "ssh_success":      rpi_ip not in rpi_errors,
                    "ssh_error":        rpi_errors.get(rpi_ip),
                    "hgw": (
                        self._build_hgw_node(
                            hgw_ip=hgw_ip,
                            via_rpi_ip=rpi_ip,
                            instance_key=instance_key,
                            hgw_fact=hgw_fact,
                            hgw_errors=hgw_errors,
                        )
                        if hgw_ip else None
                    ),
                })

            result_switches.append({
                "ip":          sw.ip,
                "name":        sw.name,
                "enabled":     sw.enabled,
                "model":       sw_fact.model if sw_fact else sw.model,
                "firmware":    sw_fact.firmware_version if sw_fact else sw.firmware_version,
                "uptime":      sw_fact.uptime if sw_fact else sw.uptime,
                "mac_address": sw_fact.mac_address if sw_fact else sw.mac_address,
                "cpu_5s":      sw_fact.cpu_5s if sw_fact else None,
                "mem_free_kb": sw_fact.mem_free_kb if sw_fact else None,
                "ssh_error":   switch_errors.get(sw.ip),
                "rpi_count":   len(rpis_on_switch),
                "rpis":        rpis_on_switch,
            })

        # Unassigned RPis
        unassigned = []
        for entry in rpi_entries:
            if entry.ip_mgmt not in all_assigned_rpis:
                rpi_db = self.rpi_repo.get_by_ip(entry.ip_mgmt)
                unassigned.append({
                    "ip_mgmt":          entry.ip_mgmt,
                    "mac":              entry.mac,
                    "label":            entry.label,
                    "last_ssh_success": rpi_db.last_ssh_success if rpi_db else None,
                    "last_ssh_error":   rpi_db.last_ssh_error if rpi_db else None,
                    "hgw_ip":           rpi_db.hgw_ip if rpi_db else None,
                })

        run = self.discovery_repo.get_run(run_id)

        return {
            "run_id":          run_id,
            "run_status":      run.status if run else None,
            "run_started_at":  run.started_at.isoformat() if run and run.started_at else None,
            "run_finished_at": run.finished_at.isoformat() if run and run.finished_at else None,
            "switches":        result_switches,
            "unassigned_rpis": unassigned,
            "total_rpis":      len(rpi_entries),
            "total_assigned":  len(all_assigned_rpis),
            "errors": [
                {
                    "device_type": e.device_type,
                    "device_ip":   e.device_ip,
                    "stage":       e.stage,
                    "error":       e.error,
                }
                for e in errors
            ],
        }

    def _build_hgw_node(
        self,
        hgw_ip: str,
        via_rpi_ip: str,
        instance_key: Optional[str],
        hgw_fact,
        hgw_errors: dict,
    ) -> dict:
        # With new discovery, HGW errors are keyed by instance_key (MAC gateway or fallback)
        err_key = instance_key or hgw_ip

        return {
            "ip":               hgw_ip,
            "via_rpi_ip":       via_rpi_ip,
            "instance_key":     instance_key,  # NEW: critical to avoid IP-based merges
            "network":          _get_network_prefix(hgw_ip),
            "manufacturer":     hgw_fact.manufacturer     if hgw_fact else None,
            "model_name":       hgw_fact.model_name       if hgw_fact else None,
            "software_version": hgw_fact.software_version if hgw_fact else None,
            "serial_number":    hgw_fact.serial_number    if hgw_fact else None,
            "external_ip":      hgw_fact.external_ip      if hgw_fact else None,
            "uptime_seconds":   hgw_fact.uptime_seconds   if hgw_fact else None,
            "mem_free_kb":      hgw_fact.mem_free_kb      if hgw_fact else None,
            "mem_total_kb":     hgw_fact.mem_total_kb     if hgw_fact else None,
            "device_status":    hgw_fact.device_status    if hgw_fact else None,
            "ssh_success":      err_key not in hgw_errors,
            "ssh_error":        hgw_errors.get(err_key),
        }


# ── Helper ───────────────────────────────────────────────────────────────────

def _get_network_prefix(ip: str) -> Optional[str]:
    if not ip:
        return None
    parts = ip.split(".")
    if len(parts) != 4:
        return None
    return f"{parts[0]}.{parts[1]}.{parts[2]}.x"