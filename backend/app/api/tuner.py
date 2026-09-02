from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from app.api._hdhomerun_settings import get_hdhomerun_settings
from app.auth import get_current_user
from app.dvr.builtin import watch
from app.dvr.builtin.capture import capture_pipeline
from app.dvr.builtin.tuner_allocator import tuner_allocator
from app.integrations import hdhomerun_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/tuner", tags=["tuner"], dependencies=[Depends(get_current_user)])


async def _enrich_tuner_status(
    tuners: list[dict[str, Any]], settings: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    enriched = []
    dvr_host = hdhomerun_client._normalize_host(settings.get("dvr_host")) if settings and settings.get("dvr_host") else None

    for tuner in tuners:
        tuner_copy = dict(tuner)
        if not tuner_copy.get("in_use"):
            tuner_copy["client"] = None
            tuner_copy["warning"] = None
            enriched.append(tuner_copy)
            continue

        ch_num = tuner_copy.get("channel_number")
        capture = await capture_pipeline.get_active_capture_by_channel(ch_num) if ch_num else None

        if capture is not None:
            if not capture.is_temporary:
                # Scheduled DVR recording
                title = capture.title
                tuner_copy["client"] = {
                    "type": "scheduled_recording",
                    "name": f"Recording: {title}",
                    "ip": None,
                    "hostname": None,
                    "details": f"Scheduled recording '{title}'",
                    "recording_id": capture.recording_id,
                    "scheduled_id": capture.scheduled_id,
                    "is_recording": True,
                    "viewers": [],
                }
                tuner_copy["warning"] = {
                    "severity": "danger",
                    "message": f"Tuner {tuner_copy['index']} is currently recording '{title}'. Terminating will stop and save this recording early.",
                }
            else:
                # Live watch session
                sessions = await watch.get_watch_sessions_for_recording(capture.recording_id)
                viewers = [
                    {"user_name": s.user_name or "Unknown User", "client_ip": s.client_ip}
                    for s in sessions
                ]
                if viewers:
                    viewer_names = ", ".join(v["user_name"] for v in viewers)
                else:
                    viewer_names = "Live TV Viewer"
                tuner_copy["client"] = {
                    "type": "live_watch",
                    "name": viewer_names,
                    "ip": viewers[0]["client_ip"] if viewers else None,
                    "hostname": None,
                    "details": f"Live TV on {ch_num}" + (f" ({capture.title})" if capture.title and capture.title != capture.channel_name else ""),
                    "recording_id": capture.recording_id,
                    "scheduled_id": None,
                    "is_recording": False,
                    "viewers": viewers,
                }
                tuner_copy["warning"] = {
                    "severity": "warning",
                    "message": f"Tuner {tuner_copy['index']} is in use for Live TV ({viewer_names}). Terminating will disconnect active viewers.",
                }
        else:
            # External client or hardware lock
            target_ip = tuner_copy.get("target_ip")
            hostname = await hdhomerun_client.resolve_hostname(target_ip) if target_ip else None
            is_dvr_server = bool(
                target_ip and dvr_host and (target_ip == dvr_host or (hostname and dvr_host in hostname))
            )

            dvr_ssh_viewers: list[dict[str, Any]] = []
            if is_dvr_server:
                display_name = f"HDHomeRun RECORD ({target_ip})"
                details = f"Official HDHomeRun RECORD engine on {target_ip} (proxies streams for official apps on iPhone, Apple TV, Android, etc.)"
                warning_message = f"Tuner {tuner_copy['index']} is streaming through the official HDHomeRun RECORD engine on {target_ip}. Terminating will disconnect official app viewers or stop an active recording."

                if settings and hdhomerun_client.is_dvr_ssh_configured(settings):
                    ssh_clients = await hdhomerun_client.fetch_dvr_ssh_clients(settings)
                    if ssh_clients:
                        client_names = [c["hostname"] or c["ip"] for c in ssh_clients]
                        dvr_ssh_viewers = [
                            {"user_name": name, "client_ip": c["ip"]}
                            for name, c in zip(client_names, ssh_clients, strict=True)
                        ]
                        details = f"Client: {', '.join(client_names)} via HDHomeRun RECORD engine ({target_ip})"
                        warning_message = (
                            f"Tuner {tuner_copy['index']} is streaming to {', '.join(client_names)} through the "
                            f"HDHomeRun RECORD engine on {target_ip}. Terminating will disconnect these viewers or "
                            "stop an active recording."
                        )
            elif target_ip:
                display_name = f"{target_ip} ({hostname})" if hostname else target_ip
                details = f"External stream to {display_name}"
                warning_message = f"Tuner {tuner_copy['index']} is streaming to external client {display_name}. Terminating will force the HDHomeRun hardware to clear the target and release the tuner."
            else:
                display_name = "External client"
                details = "External client or hardware lock"
                warning_message = f"Tuner {tuner_copy['index']} is streaming to external client. Terminating will force the HDHomeRun hardware to clear the target and release the tuner."

            tuner_copy["client"] = {
                "type": "dvr_proxy" if is_dvr_server else "external",
                "name": display_name,
                "ip": target_ip,
                "hostname": hostname,
                "details": details,
                "recording_id": None,
                "scheduled_id": None,
                "is_recording": False,
                "viewers": dvr_ssh_viewers,
            }
            tuner_copy["warning"] = {
                "severity": "warning",
                "message": warning_message,
            }

        enriched.append(tuner_copy)
    return enriched


@router.get("/lineup")
async def get_lineup():
    settings = await get_hdhomerun_settings()
    if not hdhomerun_client.is_tuner_configured(settings):
        raise HTTPException(status_code=404, detail="Tuner not configured")
    return await hdhomerun_client.fetch_lineup(settings)


@router.get("/info")
async def get_tuner_info():
    settings = await get_hdhomerun_settings()
    if not hdhomerun_client.is_tuner_configured(settings):
        raise HTTPException(status_code=404, detail="Tuner not configured")
    discover = await hdhomerun_client.fetch_discover(settings)
    return {
        "friendly_name": discover.get("FriendlyName", "HDHomeRun"),
        "model_number": discover.get("ModelNumber"),
        "firmware_version": discover.get("FirmwareVersion"),
        "tuner_count": discover.get("TunerCount"),
    }


@router.get("/status")
async def get_status():
    settings = await get_hdhomerun_settings()
    if not hdhomerun_client.is_tuner_configured(settings):
        raise HTTPException(status_code=404, detail="Tuner not configured")
    raw_status = await hdhomerun_client.fetch_tuner_status(settings)
    return await _enrich_tuner_status(raw_status, settings)


@router.post("/{index}/terminate")
async def terminate_tuner(index: int, user: dict[str, Any] = Depends(get_current_user)):
    settings = await get_hdhomerun_settings()
    if not hdhomerun_client.is_tuner_configured(settings):
        raise HTTPException(status_code=404, detail="Tuner not configured")

    raw_statuses = await hdhomerun_client.fetch_tuner_status(settings)
    matching_tuner = next((t for t in raw_statuses if t["index"] == index), None)

    ch_num = matching_tuner.get("channel_number") if matching_tuner else None
    if ch_num:
        capture = await capture_pipeline.get_active_capture_by_channel(ch_num)
        if capture is not None:
            if capture.is_temporary:
                await watch.finalize_capture_release(capture.recording_id, ch_num)
            else:
                await capture_pipeline.stop_capture(capture.recording_id)
                await tuner_allocator.release_tuner(capture.recording_id)

    # Release on physical hardware
    await hdhomerun_client.release_hardware_tuner(settings, index)

    # Return refreshed and enriched status
    refreshed_raw = await hdhomerun_client.fetch_tuner_status(settings)
    refreshed_enriched = await _enrich_tuner_status(refreshed_raw, settings)
    return {
        "ok": True,
        "message": f"Tuner {index} released successfully.",
        "tuners": refreshed_enriched,
    }
