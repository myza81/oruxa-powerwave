"""Coverage for DEV/PROD Compose isolation.

Docker is not available on every developer machine, so these tests resolve
Compose's ``${VAR:-default}`` / ``${VAR:?error}`` interpolation directly and
inspect the result. CI additionally renders both overlays with real Compose.
"""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "compose.yaml"
DEV = ROOT / "compose.dev.yaml"
PROD = ROOT / "compose.prod.yaml"
DEPLOY = ROOT / "scripts" / "deploy.sh"

PROD_PORTS = {"backend": 8100, "frontend": 8101}
DEV_PORTS = {"backend": 8200, "frontend": 8201}


class MissingVariable(Exception):
    def __init__(self, name, message):
        super().__init__(f"required variable {name} is missing a value: {message}")
        self.name = name


def _closing_brace(text: str, start: int) -> int:
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("unbalanced ${ in compose file")


def interpolate(text: str, env: dict) -> str:
    """Resolve Compose variable syntax, including nested defaults."""
    out, i = [], 0
    while i < len(text):
        if text[i] == "$" and text[i + 1 : i + 2] == "{":
            end = _closing_brace(text, i + 1)
            out.append(_resolve(text[i + 2 : end], env))
            i = end + 1
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def _resolve(expr: str, env: dict) -> str:
    m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)(?::([-?])(.*))?$", expr, re.S)
    assert m, f"unparsable expression: {expr}"
    name, op, arg = m.groups()

    if env.get(name):
        return env[name]
    if op == "-":
        return interpolate(arg or "", env)
    if op == "?":
        raise MissingVariable(name, arg or "")
    return ""


def load(path: Path, env: dict | None = None) -> dict:
    return yaml.safe_load(interpolate(path.read_text(), env or {}))


def published_port(entry: str) -> int:
    """'127.0.0.1:8201:80' -> 8201"""
    return int(entry.split(":")[-2])


def ports_of(doc: dict) -> dict:
    return {
        name: published_port(svc["ports"][0])
        for name, svc in doc["services"].items()
        if svc.get("ports")
    }


def images_of(doc: dict) -> dict:
    return {name: svc["image"] for name, svc in doc["services"].items()}


def data_mount(doc: dict) -> str:
    """Source of whatever is mounted at /data."""
    for entry in doc["services"]["backend"]["volumes"]:
        if entry.split(":")[-1].rstrip("/") == "/data" or entry.endswith(":/data"):
            return entry.rsplit(":/data", 1)[0]
    raise AssertionError("no /data mount found")


PROD_ENV = {
    "POWERWAVE_DATA_PATH": "/srv/oruxa/data/powerwave",
    "POWERWAVE_UID": "1000",
    "POWERWAVE_GID": "1000",
    "API_BASE_URL": "https://api.powerwave.example",
}


class TestNoFixedContainerNames:
    @pytest.mark.parametrize("path", [BASE, DEV, PROD], ids=lambda p: p.name)
    def test_no_container_name_declared(self, path):
        assert "container_name" not in path.read_text()

    def test_deploy_script_uses_no_container_names(self):
        source = DEPLOY.read_text()

        assert "docker logs" not in source
        assert "powerwave-backend" not in source
        assert "powerwave-frontend" not in source

    def test_deploy_script_addresses_services_by_name(self):
        assert "logs --tail=50 backend" in DEPLOY.read_text()


class TestProjectNames:
    def test_dev_overlay_declares_its_project(self):
        assert load(DEV)["name"] == "powerwave-dev"

    def test_prod_overlay_declares_its_project(self):
        assert load(PROD, PROD_ENV)["name"] == "powerwave-prod"

    def test_base_declares_no_project(self):
        assert "name" not in load(BASE)

    def test_projects_differ(self):
        assert load(DEV)["name"] != load(PROD, PROD_ENV)["name"]

    @pytest.mark.parametrize("target", ["dev", "prod"])
    def test_deploy_script_derives_the_same_project_name(self, target):
        """deploy.sh and the overlays must not drift apart."""
        assert 'PROJECT="powerwave-${TARGET}"' in DEPLOY.read_text()

        overlay = DEV if target == "dev" else PROD
        env = {} if target == "dev" else PROD_ENV
        assert load(overlay, env)["name"] == f"powerwave-{target}"

    def test_deploy_script_passes_the_project_to_compose(self):
        assert '-p "$PROJECT"' in DEPLOY.read_text()


class TestPortIsolation:
    def test_dev_defaults(self):
        assert ports_of(load(DEV)) == DEV_PORTS

    def test_prod_defaults(self):
        assert ports_of(load(PROD, PROD_ENV)) == PROD_PORTS

    def test_dev_and_prod_ports_are_disjoint(self):
        dev = set(ports_of(load(DEV)).values())
        prod = set(ports_of(load(PROD, PROD_ENV)).values())

        assert dev.isdisjoint(prod)

    def test_base_publishes_no_ports(self):
        """Host ports belong to overlays; the base stays portable."""
        for svc in load(BASE)["services"].values():
            assert "ports" not in svc

    @pytest.mark.parametrize("overlay,env", [(DEV, {}), (PROD, PROD_ENV)])
    def test_ports_bind_to_loopback_by_default(self, overlay, env):
        doc = load(overlay, env)
        for svc in doc["services"].values():
            for entry in svc.get("ports", []):
                assert entry.startswith("127.0.0.1:")

    def test_ports_are_overridable(self):
        doc = load(DEV, {"BACKEND_PORT": "9200", "FRONTEND_PORT": "9201"})

        assert ports_of(doc) == {"backend": 9200, "frontend": 9201}


class TestImageIsolation:
    """Image tags must be target-qualified.

    The project name isolates containers, networks and volumes, but the image
    tag is shared state: without TARGET in the tag, a DEV build would overwrite
    the tag a PROD stack is running from on the same host.
    """

    def test_dev_images_are_target_qualified(self):
        images = images_of(load(BASE, {"TARGET": "dev"}))

        assert images == {
            "frontend": "powerwave-frontend:dev-local",
            "backend": "powerwave-backend:dev-local",
        }

    def test_prod_images_are_target_qualified(self):
        images = images_of(load(BASE, {"TARGET": "prod"}))

        assert images == {
            "frontend": "powerwave-frontend:prod-local",
            "backend": "powerwave-backend:prod-local",
        }

    @pytest.mark.parametrize("service", ["backend", "frontend"])
    def test_dev_and_prod_images_differ(self, service):
        dev = images_of(load(BASE, {"TARGET": "dev"}))[service]
        prod = images_of(load(BASE, {"TARGET": "prod"}))[service]

        assert dev != prod

    def test_no_image_tag_is_shared_between_targets(self):
        dev = set(images_of(load(BASE, {"TARGET": "dev"})).values())
        prod = set(images_of(load(BASE, {"TARGET": "prod"})).values())

        assert dev.isdisjoint(prod)

    @pytest.mark.parametrize("target", ["dev", "prod"])
    def test_app_version_is_included_in_the_tag(self, target):
        env = {"TARGET": target, "APP_VERSION": "abc1234"}

        for image in images_of(load(BASE, env)).values():
            assert image.endswith(f":{target}-abc1234")

    def test_same_version_across_targets_still_yields_distinct_tags(self):
        version = {"APP_VERSION": "abc1234"}
        dev = images_of(load(BASE, {**version, "TARGET": "dev"}))
        prod = images_of(load(BASE, {**version, "TARGET": "prod"}))

        assert set(dev.values()).isdisjoint(set(prod.values()))

    def test_overlays_do_not_override_the_image(self):
        """Tag policy lives in one place, so it cannot drift per environment."""
        for path, env in [(DEV, {}), (PROD, PROD_ENV)]:
            for svc in load(path, env)["services"].values():
                assert "image" not in svc

    def test_deploy_script_exports_target_for_interpolation(self):
        assert "export APP_VERSION TARGET" in DEPLOY.read_text()


class TestStorageIsolation:
    def test_prod_requires_an_explicit_data_path(self):
        with pytest.raises(MissingVariable) as exc:
            load(PROD, {k: v for k, v in PROD_ENV.items()
                        if k != "POWERWAVE_DATA_PATH"})

        assert exc.value.name == "POWERWAVE_DATA_PATH"

    def test_prod_uses_the_configured_host_path(self):
        assert data_mount(load(PROD, PROD_ENV)) == "/srv/oruxa/data/powerwave"

    def test_dev_defaults_to_a_named_volume_not_a_host_path(self):
        mount = data_mount(load(DEV))

        assert not mount.startswith("/")
        assert mount == "powerwave-data"

    def test_dev_and_prod_storage_differ_by_default(self):
        assert data_mount(load(DEV)) != data_mount(load(PROD, PROD_ENV))

    def test_dev_accepts_its_own_host_path(self):
        dev = load(DEV, {"POWERWAVE_DATA_PATH": "/srv/oruxa/data/powerwave-dev"})

        assert data_mount(dev) == "/srv/oruxa/data/powerwave-dev"
        assert data_mount(dev) != data_mount(load(PROD, PROD_ENV))


class TestProductionSafeguardsIntact:
    @pytest.mark.parametrize(
        "variable",
        ["API_BASE_URL", "POWERWAVE_DATA_PATH", "POWERWAVE_UID", "POWERWAVE_GID"],
    )
    def test_missing_required_variable_fails_rendering(self, variable):
        env = {k: v for k, v in PROD_ENV.items() if k != variable}

        with pytest.raises(MissingVariable) as exc:
            load(PROD, env)

        assert exc.value.name == variable

    def test_prod_declares_production_environment(self):
        services = load(PROD, PROD_ENV)["services"]

        assert services["frontend"]["environment"]["ENVIRONMENT"] == "production"
        assert services["backend"]["environment"]["ENVIRONMENT"] == "production"

    def test_prod_keeps_the_shared_external_network(self):
        doc = load(PROD, PROD_ENV)

        assert doc["networks"]["oruxa-backend"]["external"] is True
        assert "oruxa-backend" in doc["services"]["backend"]["networks"]

    def test_prod_runs_as_a_non_root_user(self):
        assert load(PROD, PROD_ENV)["services"]["backend"]["user"] == "1000:1000"


class TestIndependentRendering:
    def test_dev_renders_with_no_environment_at_all(self):
        doc = load(DEV)

        assert doc["services"]["backend"]["environment"]["ENVIRONMENT"] == "development"

    def test_prod_renders_with_its_required_environment(self):
        assert load(PROD, PROD_ENV)["services"]

    def test_base_renders_alone_and_stays_portable(self):
        text = BASE.read_text()

        assert "/srv/" not in text
        assert "oruxa-backend" not in text
        assert "name:" not in text.split("services:")[0]

    def test_no_postgres_in_the_application_stack(self):
        for path in (BASE, DEV, PROD):
            text = path.read_text().lower()
            assert "postgres" not in text
            assert "5432" not in text
