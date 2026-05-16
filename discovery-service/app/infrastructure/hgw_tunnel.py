# app/infrastructure/hgw_tunnel.py
"""
TCP bridge to an HGW that is only reachable from inside a Docker container on the RPi.

The RPi host opens: docker exec -i <container> /bin/bash -c 'exec 3<>/dev/tcp/<hgw_ip>/<port>; cat <&3 >&3'
The resulting Paramiko channel is used as `sock=` for Paramiko SSH or telnetlib.
"""
from __future__ import annotations

import logging
import re
import shlex
import time
from typing import Optional

import paramiko

logger = logging.getLogger(__name__)

_SAFE_CONT = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]+$")
_SAFE_IP = re.compile(r"^(?:[0-9]{1,3}\.){3}[0-9]{1,3}$")


def sanitize_docker_container_ref(cid: str) -> str:
    c = (cid or "").strip()
    if not c or len(c) > 128 or not _SAFE_CONT.match(c):
        raise ValueError("invalid docker container reference")
    return c


def sanitize_ipv4(ip: str) -> str:
    s = (ip or "").strip()
    if not _SAFE_IP.match(s):
        raise ValueError("invalid ipv4 for tunnel target")
    parts = [int(x) for x in s.split(".")]
    if any(p > 255 for p in parts):
        raise ValueError("invalid ipv4 octet")
    return s


def open_tcp_through_docker_exec(
    rpi_client: paramiko.SSHClient,
    container_id: str,
    dest_host: str,
    dest_port: int,
    timeout: float = 60.0,
) -> paramiko.Channel:
    """
    On the RPi (rpi_client), run docker exec and expose a raw TCP byte stream to dest_host:dest_port
    as seen from inside the container.
    """
    cid = sanitize_docker_container_ref(container_id)
    hip = sanitize_ipv4(dest_host)
    if dest_port < 1 or dest_port > 65535:
        raise ValueError("invalid port")

    transport = rpi_client.get_transport()
    if transport is None:
        raise ConnectionError("RPi SSH transport is not active")

    chan = transport.open_session()
    chan.settimeout(timeout)

    inner = f"exec 3<>/dev/tcp/{hip}/{int(dest_port)}; cat <&3 >&3"
    quoted_inner = shlex.quote(inner)
    remote_cmd = f"docker exec -i {cid} /bin/bash -c {quoted_inner}"

    logger.info(
        "[HGW_TUNNEL] docker exec TCP bridge container=%s -> %s:%s",
        cid,
        hip,
        dest_port,
    )
    chan.exec_command(remote_cmd)
    time.sleep(0.25)
    return chan


def open_hgw_tunnel_sock(
    rpi_client: paramiko.SSHClient,
    hgw_host: str,
    hgw_port: int,
    via_docker_container_id: Optional[str],
) -> paramiko.Channel:
    """
    Either classic direct-tcpip from the RPi host, or docker-exec bridge when via_docker_container_id is set.
    """
    if via_docker_container_id:
        return open_tcp_through_docker_exec(
            rpi_client,
            via_docker_container_id,
            hgw_host,
            hgw_port,
            timeout=60.0,
        )

    transport = rpi_client.get_transport()
    if transport is None:
        raise ConnectionError("RPi SSH transport is not active")
    return transport.open_channel(
        "direct-tcpip",
        (hgw_host, hgw_port),
        ("127.0.0.1", 0),
    )
