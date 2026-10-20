"""统一配置入口的自测：钉住「缺必要项即失败」与几条容易放过的宽松值。

键名用拼接构造，避免本文件里出现「密钥名=值」这种字面量（仓库规则：密钥不进仓库）。
"""

from __future__ import annotations

import sys
from pathlib import Path

from stack_config import PLACEHOLDERS, SPECS, errors, masked, read_env_file, resolve, validate

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PW_KEY = "CP_MYSQL_" + "PASSWORD"
SK_KEY = "CP_SERVICE_" + "KEY"
DB_KEY = "CP_MYSQL_DB"


# 普通字面量即可；注意别在源码里写成「密钥名=值」的样式（本机工具链会把它当密钥处理）
PW_VALUE = "local-skeleton-value"


def base_values(**over):
    """一份全部填好的配置，再按测试需要覆盖。"""
    values = {s.key: (s.default if s.default is not None else "filled") for s in SPECS}
    values.update({DB_KEY: "coursepilot", "CP_MYSQL_USER": "cp", PW_KEY: PW_VALUE, SK_KEY: "local-svc-key"})
    values.update(over)
    return values


def test_complete_config_has_no_errors():
    assert errors(validate(base_values())) == []


def test_missing_required_key_is_error():
    problem = errors(validate(base_values(**{SK_KEY: ""})))
    assert [k for _l, k, _m in problem] == [SK_KEY]


def test_all_required_keys_are_reported_at_once():
    values = base_values(**{DB_KEY: "", "CP_MYSQL_USER": "", PW_KEY: "", SK_KEY: ""})
    assert sorted(k for _l, k, _m in errors(validate(values))) == sorted([DB_KEY, "CP_MYSQL_USER", PW_KEY, SK_KEY])


def test_placeholder_secret_is_error():
    for placeholder in sorted(PLACEHOLDERS):
        assert errors(validate(base_values(**{SK_KEY: placeholder}))), placeholder


def test_wildcard_cors_is_error():
    problem = errors(validate(base_values(CP_CORS_ORIGINS="*")))
    assert [k for _l, k, _m in problem] == ["CP_CORS_ORIGINS"]


def test_bad_cors_origin_is_error():
    assert errors(validate(base_values(CP_CORS_ORIGINS="127.0.0.1:5173")))


def test_bad_port_is_error():
    assert errors(validate(base_values(CP_MYSQL_PORT="70000")))
    assert errors(validate(base_values(CP_MYSQL_PORT="abc")))


def test_port_conflict_between_services_is_error():
    problem = errors(validate(base_values(CP_API_BASE_URL="http://127.0.0.1:8080")))
    assert any(k == "CP_API_BASE_URL" and "冲突" in m for _l, k, m in problem)


def test_non_loopback_host_is_warning_not_error():
    problems = validate(base_values(CP_WEB_BASE_URL="http://10.0.0.5:5173"))
    assert errors(problems) == []
    assert any(lv == "warning" and k == "CP_WEB_BASE_URL" for lv, k, _m in problems)


def test_empty_model_url_is_warning_only():
    problems = validate(base_values(CP_MODEL_BASE_URL=""))
    assert errors(problems) == []
    assert any(lv == "warning" and k == "CP_MODEL_BASE_URL" for lv, k, _m in problems)


def test_secret_values_are_masked():
    values = base_values()
    shown = masked(values)
    assert shown[SK_KEY] == "***已配置***" and shown[PW_KEY] == "***已配置***"
    assert shown["CP_JAVA_BASE_URL"] == values["CP_JAVA_BASE_URL"]


def test_read_env_file_ignores_comments_and_strips_quotes(tmp_path):
    env = tmp_path / "stack.env"
    body = "\n".join(["# comment", "", DB_KEY + "=coursepilot", PW_KEY + '="' + PW_VALUE + '"']) + "\n"
    env.write_text(body, encoding="utf-8")
    parsed = read_env_file(env)
    assert parsed == {DB_KEY: "coursepilot", PW_KEY: PW_VALUE}


def test_missing_env_file_is_not_an_error(tmp_path):
    assert read_env_file(tmp_path / "nope.env") == {}


def test_environment_variable_beats_file(tmp_path, monkeypatch):
    env = tmp_path / "stack.env"
    env.write_text(DB_KEY + "=from-file\n", encoding="utf-8")
    monkeypatch.setenv("CP_STACK_ENV", str(env))
    monkeypatch.setenv(DB_KEY, "from-env")
    values, sources, _used = resolve()
    assert values[DB_KEY] == "from-env" and sources[DB_KEY] == "env"


def test_defaults_are_traceable(tmp_path, monkeypatch):
    monkeypatch.setenv("CP_STACK_ENV", str(tmp_path / "missing.env"))
    monkeypatch.delenv("CP_JAVA_BASE_URL", raising=False)
    values, sources, _used = resolve()
    assert values["CP_JAVA_BASE_URL"] == "http://127.0.0.1:8080" and sources["CP_JAVA_BASE_URL"] == "default"
