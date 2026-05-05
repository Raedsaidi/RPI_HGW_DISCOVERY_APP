import json
import logging
from typing import Optional
from sqlalchemy.orm import Session

from app.repositories.discovery_repo import DiscoveryRepository
from app.repositories.switch_repo import SwitchRepository
from app.repositories.rpi_repo import RpiRepository
from app.repositories.hgw_repo import HgwRepository
from app.parsers.piserver_parser import parse_piserver

logger = logging.getLogger(__name__)


class TopologyService:
    """Build topology tree: Switch → RPi → HGW."""

    def __init__(self, db: Session):
        self.db = db
        self.discovery_repo = DiscoveryRepository(db)
        self.switch_repo = SwitchRepository(db)
        self.rpi_repo = RpiRepository(db)
        self.hgw_repo = HgwRepository(db)

    def get_topology_for_run(self, run_id: int) -> dict:
        """
        Build topology view:
        {
          "run_id": ...,
          "switches": [
            {
              "ip": "172.16.55.238",
              "name": "Switch 1",
              "model": "GS728TPv2",
              ...
              "rpis": [
                {
                  "ip_mgmt": "172.16.55.11",
                  "hostname": "raspberrypi",
                  "switch_port": "g1",
                  "hgw": { "ip": "192.168.1.1", ... } | null,
                  "ssh_success": true,
                  "ssh_error": null,
                  ...
                }
              ]
            }
          ],
          "unassigned_rpis": [...],
          "errors": [...]
        }
        """
        # Get piserver snapshot for this run
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

        # MAC entries for this run
        mac_entries = self.switch_repo.get_mac_entries_for_run(run_id)

        # Build switch_ip → {rpi_ip → port}
        switch_rpi_map: dict[str, dict[str, str]] = {}
        for entry in mac_entries:
            mac_u = entry.mac.upper()
            if mac_u in piserver_mac_to_ip:
                rpi_ip = piserver_mac_to_ip[mac_u]
                if entry.switch_ip not in switch_rpi_map:
                    switch_rpi_map[entry.switch_ip] = {}
                switch_rpi_map[entry.switch_ip][rpi_ip] = entry.port

        # RPi facts for this run
        rpi_facts = self.rpi_repo.get_facts_for_run(run_id)
        rpi_fact_map = {f.rpi_ip_mgmt: f for f in rpi_facts}

        # HGW facts for this run
        hgw_facts = self.hgw_repo.get_facts_for_run(run_id)
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
                if not existing or (fact.collected_at and existing.collected_at and fact.collected_at > existing.collected_at):
                    hgw_fact_path_map[key] = fact

            if fact.hgw_ip and fact.via_rpi_ip:
                path_key = f"{fact.hgw_ip}|{fact.via_rpi_ip}"
                existing = hgw_fact_path_map.get(path_key)
                if not existing or (fact.collected_at and existing.collected_at and fact.collected_at > existing.collected_at):
                    hgw_fact_path_map[path_key] = fact

            if fact.hgw_ip and hgw_ip_counts.get(fact.hgw_ip, 0) == 1:
                existing_ip = hgw_fact_ip_map.get(fact.hgw_ip)
                if not existing_ip or (fact.collected_at and existing_ip.collected_at and fact.collected_at > existing_ip.collected_at):
                    hgw_fact_ip_map[fact.hgw_ip] = fact

        # Errors
        errors = self.discovery_repo.get_errors_for_run(run_id)
        rpi_errors = {
            e.device_ip: e.error
            for e in errors
            if e.device_type == "rpi"
        }
        hgw_errors = {
            e.device_ip: e.error
            for e in errors
            if e.device_type == "hgw"
        }
        switch_errors = {
            e.device_ip: e.error
            for e in errors
            if e.device_type == "switch"
        }

        # Build switches list
        switches_configured = self.switch_repo.list_all()
        result_switches = []
        all_assigned_rpis = set()

        for sw in switches_configured:
            sw_fact = self.switch_repo.get_last_fact(sw.ip)
            rpi_port_map = switch_rpi_map.get(sw.ip, {})

            rpis_on_switch = []
            for rpi_ip, port in sorted(rpi_port_map.items()):
                all_assigned_rpis.add(rpi_ip)
                rpi_fact = rpi_fact_map.get(rpi_ip)

                # hgw_ip vient maintenant de ip r s (valeur réelle)
                hgw_ip = rpi_fact.hgw_ip if rpi_fact else None
                hgw_fact = None
                if hgw_ip:
                    hgw_fact = hgw_fact_path_map.get(f"{hgw_ip}|{rpi_ip}")
                    if not hgw_fact:
                        hgw_fact = hgw_fact_ip_map.get(hgw_ip)

                rpis_on_switch.append({
                    "ip_mgmt": rpi_ip,
                    "mac": piserver_ip_to_mac.get(rpi_ip),
                    "label": piserver_ip_to_label.get(rpi_ip),
                    "switch_port": port,
                    "hostname": rpi_fact.hostname if rpi_fact else None,
                    "model": rpi_fact.model if rpi_fact else None,
                    "os_pretty": rpi_fact.os_pretty if rpi_fact else None,
                    "temp_celsius": rpi_fact.temp_celsius if rpi_fact else None,
                    "mem_total_mb": rpi_fact.mem_total_mb if rpi_fact else None,
                    "mem_used_mb": rpi_fact.mem_used_mb if rpi_fact else None,
                    "disk_used_pct": rpi_fact.disk_used_pct if rpi_fact else None,
                    "docker_available": (
                        rpi_fact.docker_available if rpi_fact else None
                    ),
                    "ssh_success": rpi_ip not in rpi_errors,
                    "ssh_error": rpi_errors.get(rpi_ip),
                    "hgw": (
                        self._build_hgw_node(hgw_ip, hgw_fact, hgw_errors)
                        if hgw_ip
                        else None
                    ),
                })

            result_switches.append({
                "ip": sw.ip,
                "name": sw.name,
                "enabled": sw.enabled,
                "model": sw_fact.model if sw_fact else sw.model,
                "firmware": (
                    sw_fact.firmware_version
                    if sw_fact
                    else sw.firmware_version
                ),
                "uptime": sw_fact.uptime if sw_fact else sw.uptime,
                "mac_address": (
                    sw_fact.mac_address if sw_fact else sw.mac_address
                ),
                "cpu_5s": sw_fact.cpu_5s if sw_fact else None,
                "mem_free_kb": sw_fact.mem_free_kb if sw_fact else None,
                "ssh_error": switch_errors.get(sw.ip),
                "rpi_count": len(rpis_on_switch),
                "rpis": rpis_on_switch,
            })

        # Unassigned RPis (in piserver but not found on any switch)
        unassigned = []
        for entry in rpi_entries:
            if entry.ip_mgmt not in all_assigned_rpis:
                rpi_db = self.rpi_repo.get_by_ip(entry.ip_mgmt)
                unassigned.append({
                    "ip_mgmt": entry.ip_mgmt,
                    "mac": entry.mac,
                    "label": entry.label,
                    "last_ssh_success": (
                        rpi_db.last_ssh_success if rpi_db else None
                    ),
                    "last_ssh_error": (
                        rpi_db.last_ssh_error if rpi_db else None
                    ),
                    # hgw_ip en DB = valeur sauvée lors du dernier run réussi
                    "hgw_ip": rpi_db.hgw_ip if rpi_db else None,
                })

        run = self.discovery_repo.get_run(run_id)

        return {
            "run_id": run_id,
            "run_status": run.status if run else None,
            "run_started_at": (
                run.started_at.isoformat()
                if run and run.started_at
                else None
            ),
            "run_finished_at": (
                run.finished_at.isoformat()
                if run and run.finished_at
                else None
            ),
            "switches": result_switches,
            "unassigned_rpis": unassigned,
            "total_rpis": len(rpi_entries),
            "total_assigned": len(all_assigned_rpis),
            "errors": [
                {
                    "device_type": e.device_type,
                    "device_ip": e.device_ip,
                    "stage": e.stage,
                    "error": e.error,
                }
                for e in errors
            ],
        }

    def _build_hgw_node(
        self,
        hgw_ip: str,
        hgw_fact,
        hgw_errors: dict,
    ) -> dict:
        """
        Construire le nœud HGW pour la topologie.

        MODIFICATION : suppression du champ 'type' hardcodé
        (était basé sur l'ancienne logique ifconfig 192.168.x.x).
        Désormais hgw_ip est la vraie gateway issue de 'ip r s'.
        On expose directement l'IP sans reclassification artificielle.
        """
        return {
            "ip": hgw_ip,
            # ── réseau /24 extrait dynamiquement (ex: "192.168.1.x") ──
            "network": _get_network_prefix(hgw_ip),
            "manufacturer": hgw_fact.manufacturer if hgw_fact else None,
            "model_name": hgw_fact.model_name if hgw_fact else None,
            "software_version": (
                hgw_fact.software_version if hgw_fact else None
            ),
            "serial_number": hgw_fact.serial_number if hgw_fact else None,
            "external_ip": hgw_fact.external_ip if hgw_fact else None,
            "uptime_seconds": hgw_fact.uptime_seconds if hgw_fact else None,
            "mem_free_kb": hgw_fact.mem_free_kb if hgw_fact else None,
            "mem_total_kb": hgw_fact.mem_total_kb if hgw_fact else None,
            "device_status": hgw_fact.device_status if hgw_fact else None,
            "ssh_success": hgw_ip not in hgw_errors,
            "ssh_error": hgw_errors.get(hgw_ip),
        }

    def get_latest_run_id(self) -> Optional[int]:
        runs = self.discovery_repo.list_runs(skip=0, limit=1)
        return runs[0].id if runs else None


# ── Helper module-level (réutilisable) ───────────────────────────────────────

def _get_network_prefix(ip: str) -> Optional[str]:
    """
    Extraire le préfixe réseau /24 d'une IP.
    Exemple : "192.168.1.1" → "192.168.1.x"
    """
    if not ip:
        return None
    parts = ip.split(".")
    if len(parts) != 4:
        return None
    return f"{parts[0]}.{parts[1]}.{parts[2]}.x"