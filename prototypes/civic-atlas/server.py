"""Civic Atlas prototype: a local UI over a dedicated, real durable world."""
from __future__ import annotations

import argparse
import hmac
import json
import os
import sys
import threading
from collections import OrderedDict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import FastAPI, HTTPException, Query, Request  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from pydantic import BaseModel, ConfigDict  # noqa: E402
from starlette.middleware.cors import CORSMiddleware  # noqa: E402
from starlette.middleware.trustedhost import TrustedHostMiddleware  # noqa: E402

from utilsim.config import load_preset  # noqa: E402
from utilsim.gen.pipeline import generate  # noqa: E402
from utilsim.io.snapshot import build_snapshot  # noqa: E402
from utilsim.world import cruise  # noqa: E402
from utilsim.world.map_view import WorldMap  # noqa: E402
from utilsim.world.store import World  # noqa: E402


class AdvanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    townId: str
    expectedThrough: date


class TownRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    townId: str


class BillRequest(TownRequest):
    start: date
    end: date


class ReplacementRequest(TownRequest):
    commandId: str
    meterId: str
    newDeviceId: str
    workOrderId: str
    note: str


class ResolveRequest(TownRequest):
    exceptionId: str
    note: str


class FieldRequest(TownRequest):
    commandId: str
    installationId: str
    reason: str


class FieldReviewRequest(TownRequest):
    orderId: str
    note: str


def prepare_world(store: Path, houses: int, seed: str, *, showcase: bool = False,
                  reference: bool = False, town500: bool = False, preset: str | None = None) -> World:
    store.mkdir(parents=True, exist_ok=True)
    world = World(store / "world.sqlite")
    from source_binding import read_snapshot, require_binding, source_fingerprint
    if preset and world.status().get("environmentId"):
        with world.read_db() as db:
            binding = db.execute("SELECT json_extract(value,'$.atlasDesign.presetId'),"
                                 "json_extract(value,'$.atlasDesign.masterSvgSha256') FROM meta WHERE key='snapshot'").fetchone()
        if binding[0] != preset:
            raise ValueError("This preset needs its own store; the existing world was not changed.")
        import hashlib
        master = Path(__file__).parent / "web/presets" / preset / "master.svg"
        if hashlib.sha256(master.read_text(encoding="utf-8").encode("utf-8")).hexdigest() != binding[1]:
            raise ValueError("This map version differs from the saved world. Use an explicit migration or a new store; existing history was preserved.")
        require_binding(world, source_fingerprint(master.parent))
    if town500 and world.status().get("environmentId"):
        if WorldMap(world).snapshot().get("atlasDesign", {}).get("version") != "civic-atlas-town500/1":
            raise ValueError("The 500-home profile needs its own store; this existing world was not changed.")
    if not world.status().get("environmentId"):
        if preset:
            catalog = json.loads((Path(__file__).parent / "web/presets/catalog.json").read_text())
            known = {entry["id"] for entry in catalog["presets"]} | {"riverbend-500", "two-river-forest-500", "ashtown-5000"}
            if preset not in known:
                raise ValueError("Unknown or unbaked preset.")
            import hashlib

            source = Path(__file__).parent / "web/presets" / preset
            snapshot = read_snapshot(source)
            if hashlib.sha256((source / "master.svg").read_text(encoding="utf-8").encode("utf-8")).hexdigest() != snapshot["atlasDesign"]["masterSvgSha256"]:
                raise ValueError("The SVG changed since this preset was baked. Review and rebake before creating a world.")
            from quality import geometry_checks

            if any(check["status"] != "pass" for check in geometry_checks(snapshot)):
                raise ValueError("The baked preset failed geometry checks.")
            world.initialize(snapshot, snapshot["atlasDesign"]["name"], start="2026-01-01")
            require_binding(world, source_fingerprint(source, snapshot))
            world.advance("2026-01-08")
            return world
        if town500:
            from town500_world import build_town500_snapshot

            snapshot = build_town500_snapshot(seed=seed)
            (store / "source-snapshot.json").write_text(json.dumps(snapshot, separators=(",", ":")))
            world.initialize(snapshot, "Fairhaven", start="2026-01-01")
            world.advance("2026-01-08")
            return world
        if reference:
            from reference_world import build_reference_snapshot

            snapshot = build_reference_snapshot(seed=seed)
            world.initialize(snapshot, "Brookfield", start="2026-01-01")
            world.advance("2026-01-08")
            return world
        town_config = {"street_pattern": "neighborhoods", "arterial_spacing_m": 900,
                       "collector_block_m": 350, "terrain_relief_m": 6}
        if showcase:
            town_config.update({"collector_block_m": 250, "terrain_relief_m": 12,
                                "park_share": .18, "commercial_strip_m": 180,
                                "commercial_share_arterial": .08, "commercial_share_collector": .06,
                                "commercial_share_local": .01, "commercial_cluster_m": 70,
                                "industrial_lots": 1, "houses_per_school": 500})
        cfg = load_preset("village", seed=seed, houses=houses, overrides={"town": town_config})
        snapshot = build_snapshot(generate(cfg), embed_state=False)
        world.initialize(snapshot, "Brookfield", start="2026-01-01")
        world.advance("2026-01-08")
    return world


def create_app(world: World) -> FastAPI:
    app = FastAPI(title="Civic Atlas prototype", docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=os.environ.get("ATLAS_ALLOWED_HOSTS", "127.0.0.1,localhost").split(","))
    view = WorldMap(world)
    gate = threading.Lock()
    snapshot = view.snapshot()
    view = WorldMap(world, snapshot)
    from billing_bridge import BillingBridge
    billing = BillingBridge(world, snapshot)
    virtual = None

    def virtual_systems():
        nonlocal virtual
        if virtual is None:
            from virtual_systems import VirtualSystems
            virtual = VirtualSystems(world, snapshot)
        return virtual

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        token = os.environ.get("ATLAS_API_TOKEN")
        if token and request.url.path.startswith("/atlas/api/") and not hmac.compare_digest(request.headers.get("authorization", ""), "Bearer " + token):
            return JSONResponse({"detail": "An API access token is required."}, status_code=401)
        if request.method not in ("GET", "HEAD"):
            origin = request.headers.get("origin")
            allowed_origins = os.environ.get("ATLAS_ALLOWED_ORIGINS", "").split(",")
            if origin and origin != str(request.base_url).rstrip("/") and origin not in allowed_origins:
                return JSONResponse({"detail": "Use the local Civic Atlas application."}, status_code=403)
            if request.headers.get("sec-fetch-site") == "cross-site" and origin not in allowed_origins:
                return JSONResponse({"detail": "Cross-site changes are refused."}, status_code=403)
            if request.headers.get("content-type", "").split(";")[0] != "application/json":
                return JSONResponse({"detail": "Expected application/json."}, status_code=415)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def state():
        with world.read_db() as db:
            status = world._status(db)
            meta = world.metadata(db)
            days = [dict(row) for row in db.execute(
                "SELECT d.day,d.temperature,COUNT(o.id) observations FROM days d "
                "LEFT JOIN observations o ON o.day=d.day GROUP BY d.day ORDER BY d.day DESC LIMIT 30")]
            events = [dict(row) for row in db.execute(
                "SELECT sequence,day,type,subject FROM events ORDER BY sequence DESC LIMIT 40")]
            conditions = {row["condition"]: row["n"] for row in db.execute(
                "SELECT condition,COUNT(*) n FROM assets GROUP BY condition")}
            managed = db.execute("SELECT 1 FROM observation_delivery_configuration").fetchone() is not None
        controller = cruise.inspect(world)
        owner = "shared-runtime" if managed else "local-cruise" if cruise.owns_clock(controller) else "manual"
        return {**status, "daysHistory": days, "events": events, "conditions": conditions,
                "managedDelivery": managed, "settings": meta["settings"],
                "lastCompletedDay": days[0]["day"] if days else None,
                "clockOwner": owner, "manualAdvanceAllowed": owner == "manual",
                "clockReason": controller["unavailableReason"] or (
                    "Local cruise owns the clock. Cancel it in its control screen before advancing here."
                    if owner == "local-cruise" else None)}

    @app.get("/atlas/api/bootstrap")
    def bootstrap():
        return {"snapshot": snapshot, "state": state()}

    @app.get("/atlas/api/summary")
    def summary():
        return {"town": {"id": snapshot["id"], "seed": snapshot.get("seed"),
                         "name": snapshot.get("atlasDesign", {}).get("name"),
                         "homes": sum(p.get("premiseType") == "residential" for p in snapshot["premises"]),
                         "premises": len(snapshot["premises"]), "accounts": len(snapshot.get("accounts", [])),
                         "config": snapshot.get("config"), "design": snapshot.get("atlasDesign")}, "state": state()}

    @app.get("/atlas/api/state")
    def get_state():
        return state()

    @app.get("/atlas/api/quality")
    def quality():
        from quality import quality_report

        return quality_report(snapshot, world)

    @app.get("/atlas/api/premises/{identity}/history")
    def premise_history(identity: str, offset: int = Query(0, ge=0), limit: int = Query(14, ge=1, le=30)):
        record = premise(identity)
        with world.read_db() as db:
            through = world._status(db)['through']
            days = [r[0] for r in db.execute('SELECT day FROM days ORDER BY day DESC LIMIT ? OFFSET ?', (limit, offset))]
            total = db.execute('SELECT COUNT(*) FROM days').fetchone()[0]
            rows = [dict(r) for r in db.execute(
                'SELECT d.day,a.id assetId,a.commodity,a.unit,o.id observationId,o.status,'
                'o.quantity observedQuantity,t.quantity physicalQuantity FROM assets a '
                'CROSS JOIN (SELECT day FROM days ORDER BY day DESC LIMIT ? OFFSET ?) d '
                'LEFT JOIN observations o ON o.asset=a.id AND o.day=d.day '
                'LEFT JOIN truth t ON t.asset=a.id AND t.day=d.day '
                'WHERE a.premise=? ORDER BY d.day DESC,a.commodity,a.id', (limit, offset, identity))]
        return {'schemaVersion': 'civic-atlas-premise-history/1', 'townId': record['townId'],
                'premise': record['premise'], 'view': 'administrator-truth', 'through': through,
                'days': days, 'totalDays': total, 'offset': offset, 'limit': limit, 'readings': rows}

    @app.get("/atlas/api/premises/{identity}")
    def premise(identity: str):
        try:
            return view.premise(identity)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/atlas/api/advance")
    def advance(body: AdvanceRequest):
        with gate:
            try:
                with cruise.manual_control(world):
                    current = view.status()
                    if current["townId"] != body.townId:
                        raise HTTPException(409, "The selected world changed. Refresh before continuing.")
                    if current["managedDelivery"]:
                        raise HTTPException(409, "A shared runtime owns this world's clock.")
                    expected = body.expectedThrough.isoformat()
                    target = (body.expectedThrough + timedelta(days=1)).isoformat()
                    if current["through"] == expected:
                        world.advance(target)
                    elif current["through"] != target:
                        raise HTTPException(409, "This view is out of date. Refresh before advancing.")
            except (ValueError, OverflowError, cruise.BusyError) as exc:
                raise HTTPException(409, str(exc)) from exc
            # Repeating a request after a lost reply never advances a second day.
            return state()

    def verify_town(body):
        if body.townId != snapshot["id"]:
            raise HTTPException(409, "The selected world changed. Refresh before continuing.")

    @app.get("/atlas/api/billing")
    def billing_status(premise: str | None = None, offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
        try:
            return billing.inspect(premise, offset, limit)
        except ValueError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.post("/atlas/api/billing/ingest")
    def billing_ingest(body: TownRequest):
        verify_town(body)
        with gate:
            return billing.ingest()

    @app.post("/atlas/api/billing/run")
    def billing_run(body: BillRequest):
        verify_town(body)
        with gate:
            try:
                return billing.run(body.start.isoformat(), body.end.isoformat())
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.post("/atlas/api/billing/replace-meter")
    def replace_meter(body: ReplacementRequest):
        verify_town(body)
        with gate:
            try:
                with cruise.manual_control(world):
                    if view.status()["managedDelivery"]:
                        raise ValueError("The shared runtime owns physical actions for this world.")
                    return billing.replace(body.commandId, body.meterId, body.newDeviceId, body.workOrderId, body.note)
            except (ValueError, cruise.BusyError) as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.get("/atlas/api/integration")
    def integration():
        return {"localBilling": "available", "virtualSystems": virtual_systems().readiness(),
                "observationSchema": "utility-observations/2.0", "worldId": snapshot["id"],
                "exportPath": "/atlas/api/observations?start=YYYY-MM-DD&end=YYYY-MM-DD",
                "note": "Local UtilitySim tariffs and separately configured Virtual Systems recipients maintain distinct financial records. Shared automatic scheduling is not configured."}

    @app.get("/atlas/api/virtual-systems")
    def virtual_status(premise: str | None = None, offset: int = Query(0, ge=0), exceptionCode: str | None = Query(None, max_length=64), invoiceOffset: int = Query(0, ge=0)):
        with gate:
            return virtual_systems().inspect(premise, offset, exceptionCode, invoiceOffset)

    @app.post("/atlas/api/virtual-systems/initialize")
    def virtual_initialize(body: TownRequest):
        verify_town(body)
        with gate:
            try:
                return virtual_systems().initialize()
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.post("/atlas/api/virtual-systems/ingest")
    def virtual_ingest(body: TownRequest):
        verify_town(body)
        with gate:
            try:
                return virtual_systems().ingest()
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.post("/atlas/api/virtual-systems/run")
    def virtual_run(body: BillRequest):
        verify_town(body)
        with gate:
            try:
                return virtual_systems().run(body.start.isoformat(), body.end.isoformat())
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.post("/atlas/api/virtual-systems/invoice-eligible")
    def virtual_invoice_eligible(body: BillRequest):
        verify_town(body)
        with gate:
            try:
                return virtual_systems().invoice_eligible(body.start.isoformat(), body.end.isoformat())
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.post("/atlas/api/virtual-systems/resolve")
    def virtual_resolve(body: ResolveRequest):
        verify_town(body)
        with gate:
            try:
                return virtual_systems().resolve(body.exceptionId, body.note)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.post("/atlas/api/virtual-systems/repair")
    def virtual_repair(body: FieldRequest):
        verify_town(body)
        with gate:
            try:
                with cruise.manual_control(world):
                    if view.status()["managedDelivery"]:
                        raise ValueError("The shared runtime owns physical actions for this world.")
                    recipient = virtual_systems()
                    recipient.manifest()
                    with recipient.session() as (app, ledger, meta):
                        from virtual_field import repair
                        return repair(world, app, recipient.directory, body.installationId, body.reason, body.commandId)
            except (ValueError, cruise.BusyError) as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.post("/atlas/api/virtual-systems/accept-report")
    def virtual_review(body: FieldReviewRequest):
        verify_town(body)
        with gate:
            try:
                recipient = virtual_systems()
                recipient.manifest()
                with recipient.session() as (app, ledger, meta):
                    from virtual_field import accept_report
                    return accept_report(world, app, body.orderId, body.note)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc

    @app.get("/atlas/api/observations")
    def observation_export(start: date, end: date):
        if not 0 < (end - start).days <= 7:
            raise HTTPException(400, "Export one to seven days per request.")
        try:
            return world.export_v2(start.isoformat(), end.isoformat())
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    app.mount("/viewer", StaticFiles(directory=ROOT / "packages/town-viewer/dist"), name="viewer")
    app.mount("/", StaticFiles(directory=Path(__file__).parent / "web", html=True), name="atlas")
    return app


def create_library_app(store: Path):
    """One shell, isolated lazy worlds; selection never replaces a saved database."""
    from urllib.parse import parse_qs

    import anyio

    web = Path(__file__).parent / "web"
    apps = OrderedDict()
    locks = {}
    lock_gate = threading.Lock()
    load_gate = threading.Lock()
    cache_capacity = max(1, int(os.environ.get("ATLAS_MAX_LOADED_WORLDS", "1")))
    app = FastAPI(title="UtilitySim town library", docs_url=None, redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=os.environ.get("ATLAS_ALLOWED_HOSTS", "127.0.0.1,localhost").split(","))

    def catalog():
        from quality import visual_review
        from virtual_systems import configured

        value = json.loads((web / "presets/catalog.json").read_text())
        for town in value["presets"]:
            directory = web / "presets" / town["id"]
            town["baked"] = all((directory / name).is_file() or (directory / (name + ".gz")).is_file()
                                for name in ("snapshot.json", "master.svg", "geometry.json"))
            town["runtimeLoaded"] = town["id"] in apps
            town["internalVisualReview"] = visual_review(town["id"])
            town["readiness"] = {
                "sourceBaked": town["baked"],
                "zoomTiles": (directory / "tiles.json").is_file(),
                "visualReleaseApproved": town.get("visualReleaseApproved", False),
                "internalVisualQa": town.get("internalVisualReview", {}).get("status") == "passed",
                "savedWorld": (store / town["id"] / "world.sqlite").is_file(),
                "externalVirtualSystems": configured(),
            }
        return value

    def load(identity):
        with lock_gate:
            lock = locks.setdefault(identity, threading.Lock())
        with lock, load_gate:
            if identity not in apps:
                world = prepare_world(store / identity, 500, identity, preset=identity)
                apps[identity] = create_app(world)
            with lock_gate:
                selected_app = apps[identity]
                apps.move_to_end(identity)
                while len(apps) > cache_capacity:
                    apps.popitem(last=False)
            return selected_app

    class SelectionMiddleware:
        def __init__(self, inner):
            self.inner = inner

        async def __call__(self, scope, receive, send):
            token = os.environ.get("ATLAS_API_TOKEN")
            if scope["type"] == "http" and scope["path"].startswith("/atlas/api/"):
                headers = dict(scope["headers"])
                origin = headers.get(b"origin", b"").decode()
                host = headers.get(b"host", b"").decode()
                same_origin = origin == scope.get("scheme", "http") + "://" + host
                approved_origin = origin in [s for s in os.environ.get("ATLAS_ALLOWED_ORIGINS", "").split(",") if s]
                # Reject before lazy initialization, which creates saved days.
                if ((origin and not same_origin and not approved_origin) or
                    (headers.get(b"sec-fetch-site") == b"cross-site" and not approved_origin)):
                    await JSONResponse({"detail": "This origin is not allowed to access the runtime."}, status_code=403)(scope, receive, send)
                    return
                if scope["method"] not in ("GET", "HEAD") and headers.get(b"content-type", b"").split(b";")[0] != b"application/json":
                    await JSONResponse({"detail": "Expected application/json."}, status_code=415)(scope, receive, send)
                    return
            if scope["type"] == "http" and scope["path"].startswith("/atlas/api/") and token:
                supplied = dict(scope["headers"]).get(b"authorization", b"").decode()
                if not hmac.compare_digest(supplied, "Bearer " + token):
                    await JSONResponse({"detail": "An API access token is required."}, status_code=401)(scope, receive, send)
                    return
            if scope["type"] == "http" and scope["path"].startswith("/atlas/api/") and scope["path"] != "/atlas/api/catalog":
                params = parse_qs(scope.get("query_string", b"").decode())
                identity = params.get("town", [None])[0] or dict(scope["headers"]).get(b"x-atlas-town", b"").decode()
                available = {entry["id"]: entry for entry in catalog()["presets"]}
                if identity not in available:
                    await JSONResponse({"detail": "Select a town from the library."}, status_code=400)(scope, receive, send)
                    return
                if not available[identity]["baked"]:
                    await JSONResponse({"detail": "This town is configured but its map is not baked yet."}, status_code=409)(scope, receive, send)
                    return
                try:
                    selected = await anyio.to_thread.run_sync(load, identity)
                except (ValueError, OSError) as exc:
                    await JSONResponse({"detail": str(exc)}, status_code=409)(scope, receive, send)
                    return
                await selected(scope, receive, send)
                return
            await self.inner(scope, receive, send)

    @app.get("/atlas/api/catalog")
    def get_catalog():
        return catalog()

    @app.get("/")
    def home():
        return FileResponse(web / "library.html")

    app.mount("/viewer", StaticFiles(directory=ROOT / "packages/town-viewer/dist"), name="viewer")
    app.mount("/", StaticFiles(directory=web, html=True), name="library-assets")
    selected_app = SelectionMiddleware(app)
    origins = [value for value in os.environ.get("ATLAS_ALLOWED_ORIGINS", "").split(",") if value]
    if origins:
        return CORSMiddleware(selected_app, allow_origins=origins, allow_methods=["GET", "POST"],
                              allow_headers=["Content-Type", "Authorization", "X-Atlas-Town"])
    return selected_app


def main():
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--store", type=Path)
    parser.add_argument("--houses", type=int, choices=(80, 180, 320, 480))
    parser.add_argument("--seed")
    profiles = parser.add_mutually_exclusive_group()
    profiles.add_argument("--library", action="store_true", help="Serve the seven-town shell with isolated, lazy persistent worlds.")
    profiles.add_argument("--showcase", action="store_true",
                          help="Use more park land, a school at 320+ homes, and a shorter commercial core.")
    profiles.add_argument("--reference", action="store_true",
                          help="Use the curated Civic Atlas reference town with real simulation records.")
    profiles.add_argument("--town500", action="store_true",
                          help="Use Fairhaven: 500 homes plus commercial/civic/industrial sites; defaults to port 8041 and a separate store.")
    profiles.add_argument("--preset", help="Load a baked catalog SVG-led town; never generate streets at runtime.")
    args = parser.parse_args()
    if args.host not in ("127.0.0.1", "localhost") and not os.environ.get("ATLAS_API_TOKEN"):
        parser.error("A non-loopback listener requires ATLAS_API_TOKEN and explicit ATLAS_ALLOWED_HOSTS.")
    if args.library:
        uvicorn.run(create_library_app(args.store or ROOT / "out/civic-atlas-library"), host=args.host,
                    port=args.port or 8044, proxy_headers=False)
        return
    if (args.reference or args.town500 or args.preset) and args.houses is not None:
        parser.error("The curated reference town has a fixed layout; --houses applies to generated profiles.")
    default_seed = "CIVIC-ATLAS-FAIRHAVEN-01" if args.town500 else "CIVIC-ATLAS-REFERENCE-01" if args.reference else (
        "CIVIC-ATLAS-PARK-01" if args.showcase else "CIVIC-ATLAS-01")
    store = args.store or ROOT / (f"out/civic-atlas-{args.preset}-v2" if args.preset else "out/civic-atlas-town500-v2" if args.town500 else "out/civic-atlas")
    world = prepare_world(store, args.houses or (500 if args.town500 else 320 if args.showcase else 180),
                          args.seed or default_seed, showcase=args.showcase, reference=args.reference, town500=args.town500, preset=args.preset)
    print(json.dumps({"world": world.status(), "note": "Existing stores are resumed, never regenerated."}), flush=True)
    uvicorn.run(create_app(world), host=args.host, port=args.port or (8043 if args.preset == "two-river-forest-500" else 8042 if args.preset else 8041 if args.town500 else 8040), proxy_headers=False)


if __name__ == "__main__":
    main()
