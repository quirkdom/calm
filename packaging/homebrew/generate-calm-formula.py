# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "packaging",
# ]
# ///

import json
import re
import subprocess
import sys
from pathlib import Path

import tomllib  # Built-in in Python 3.11+
from packaging.markers import Marker

# Target Python version and platform
PY_VER = "3.14"
PLATFORM_14 = "macosx_14_0_arm64"
PLATFORM_15 = "macosx_15_0_arm64"
PLATFORM_26 = "macosx_26_0_arm64"

# Packages that MUST be wheels for macOS ARM64
WHEEL_ONLY = {
    "hf-xet": "cp37-abi3-macosx_11_0_arm64.whl",
    "numpy": "cp314-cp314-macosx_14_0_arm64.whl",
    "safetensors": "cp38-abi3-macosx_11_0_arm64.whl",
    "sentencepiece": "cp314-cp314-macosx_11_0_arm64.whl",
    "tokenizers": "cp39-abi3-macosx_11_0_arm64.whl",
    "calm-cli": "py3-none-any.whl",  # Main package as wheel
}

# Special handling for MLX (multiple OS versions)
MLX_PACKAGES = ["mlx", "mlx-metal"]


def get_project_info():
    """Get project name and version using 'uv version'"""
    try:
        # uv version output is like "calm-cli 0.3.0"
        output = subprocess.check_output(["uv", "version"], text=True).strip()
        parts = output.split()
        if len(parts) >= 2:
            return parts[0], parts[1]
    except Exception:
        pass
    return "calm-cli", None


def get_pylock_data():
    """Get dependency information using 'uv export --format pylock.toml'"""
    try:
        proj_root = Path.cwd()
        while (
            not (proj_root / "pyproject.toml").exists()
            and proj_root.parent != proj_root
        ):
            proj_root = proj_root.parent

        # We export without --python to get ALL wheels for ALL platforms/versions
        # This allows us to find the MLX wheels for different macOS versions in one go.
        cmd = [
            "uv",
            "export",
            "--format",
            "pylock.toml",
            "--no-dev",
            "--no-header",
            "--no-editable",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(proj_root))
        if result.returncode == 0:
            return tomllib.loads(result.stdout)
        else:
            print(f"Error running 'uv export': {result.stderr}", file=sys.stderr)
            sys.exit(1)
    except Exception as e:
        print(f"Error getting pylock data: {e}", file=sys.stderr)
        sys.exit(1)


def find_wheel_by_pattern(wheels, pattern, python_tag=None):
    """Find a wheel matching a filename pattern and optionally a python tag"""
    for w in wheels:
        filename = w["url"].split("/")[-1]

        # Exclude freethreaded wheels (t-tag)
        # These are tags like cp314t or py314t. They appear between dashes.
        # We look for a 't' at the end of a tag that starts with 'cp' or 'py'.
        if re.search(r"-(cp|py)\d+t-", filename):
            continue

        if pattern in filename:
            if python_tag:
                # Use regex to ensure exact tag match (e.g. cp314 doesn't match cp314t)
                # Matches .cp314. or -cp314- or .cp314- etc.
                match = re.search(rf"[.\-_]{re.escape(python_tag)}(?![t\d])", filename)
                if not (match or "abi3" in filename):
                    continue
            return w["url"], w["hashes"]["sha256"]
    return None, None


def find_best_macosx_arm64_wheel(wheels, python_tag=None):
    """Find the best macOS ARM64 wheel from a list of wheels"""

    # Sort wheels by macOS version (highest first)
    def mac_ver(w):
        m = re.search(r"macosx_(\d+)", w["url"])
        return int(m.group(1)) if m else 0

    sorted_wheels = sorted(wheels, key=mac_ver, reverse=True)

    # 1. Prefer exact python tag + arm64
    if python_tag:
        url, sha = find_wheel_by_pattern(sorted_wheels, "arm64", python_tag)
        if url:
            return url, sha

    # 2. Prefer exact python tag + universal2
    if python_tag:
        url, sha = find_wheel_by_pattern(sorted_wheels, "universal2", python_tag)
        if url:
            return url, sha

    # 3. Fallback to abi3 + arm64
    url, sha = find_wheel_by_pattern(sorted_wheels, "arm64", "abi3")
    if url:
        return url, sha

    # 4. Fallback to abi3 + universal2
    url, sha = find_wheel_by_pattern(sorted_wheels, "universal2", "abi3")
    if url:
        return url, sha

    # 5. Absolute fallback to any compatible macosx wheel
    url, sha = find_wheel_by_pattern(sorted_wheels, "macosx")
    if url and ("arm64" in url or "universal2" in url):
        return url, sha

    return None, None


def resolve_mlx_from_lock(pkg_data):
    """Resolve MLX wheels for multiple macOS versions from pylock data"""
    wheels = pkg_data.get("wheels", [])
    package = pkg_data["name"]
    results = {}

    platforms = {
        "26": PLATFORM_26 if package == "mlx" else "py3-none-macosx_26_0_arm64.whl",
        "15": PLATFORM_15 if package == "mlx" else "py3-none-macosx_15_0_arm64.whl",
        "14": PLATFORM_14 if package == "mlx" else "py3-none-macosx_14_0_arm64.whl",
    }

    # For mlx, we specifically need the cp314 tag if we are on Python 3.14
    # But since we want to be robust, we'll try to find the best match
    python_tag = f"cp{PY_VER.replace('.', '')}" if package == "mlx" else None

    for os_ver, pattern in platforms.items():
        url, sha = find_wheel_by_pattern(wheels, pattern, python_tag)
        if url:
            results[os_ver] = (url, sha)

    return results


def generate_formula():
    proj_name, proj_ver = get_project_info()
    pylock_data = get_pylock_data()

    target_env = {
        "sys_platform": "darwin",
        "platform_machine": "arm64",
        "python_version": PY_VER,
        "python_full_version": f"{PY_VER}.0",
        "os_name": "posix",
        "platform_system": "Darwin",
        "implementation_name": "cpython",
    }

    resources = []
    main_package = None

    for pkg_data in pylock_data.get("packages", []):
        name = pkg_data["name"]

        # Check markers
        if "marker" in pkg_data:
            try:
                marker = Marker(pkg_data["marker"])
                if not marker.evaluate(target_env):
                    continue
            except Exception:
                pass

        # Handle main package
        if name == proj_name:
            if "directory" in pkg_data:
                # Still hit PyPI for the main package sdist/wheel if it's currently editable in the lock
                if proj_ver:
                    import urllib.request

                    url = f"https://pypi.org/pypi/{name}/{proj_ver}/json"
                    try:
                        with urllib.request.urlopen(url) as response:
                            meta = json.loads(response.read())
                            urls = meta.get("urls", [])
                            sdist_url, sdist_sha = None, None
                            wheel_url, wheel_sha = None, None

                            for f in urls:
                                if f["filename"].endswith(".tar.gz"):
                                    sdist_url, sdist_sha = (
                                        f["url"],
                                        f["digests"]["sha256"],
                                    )
                                if f["filename"].endswith(
                                    WHEEL_ONLY.get(name, "py3-none-any.whl")
                                ):
                                    wheel_url, wheel_sha = (
                                        f["url"],
                                        f["digests"]["sha256"],
                                    )

                            main_package = {
                                "name": name,
                                "version": proj_ver,
                                "url": sdist_url
                                or f"https://github.com/quirkdom/calm/archive/refs/tags/v{proj_ver}.tar.gz",
                                "sha256": sdist_sha or "REPLACE_WITH_SHA256",
                                "wheel_url": wheel_url or "REPLACE_WITH_WHEEL_URL",
                                "wheel_sha": wheel_sha or "REPLACE_WITH_WHEEL_SHA256",
                            }
                    except Exception:
                        pass

                if not main_package:
                    main_package = {
                        "name": name,
                        "version": proj_ver or "0.0.0",
                        "url": f"https://github.com/quirkdom/calm/archive/refs/tags/v{proj_ver}.tar.gz"
                        if proj_ver
                        else "URL",
                        "sha256": "REPLACE_WITH_SHA256",
                        "wheel_url": "REPLACE_WITH_WHEEL_URL",
                        "wheel_sha": "REPLACE_WITH_WHEEL_SHA256",
                    }
            else:
                sdist_url = pkg_data.get("sdist", {}).get("url")
                sdist_sha = pkg_data.get("sdist", {}).get("hashes", {}).get("sha256")

                # Find best wheel for target environment
                python_tag = f"cp{PY_VER.replace('.', '')}"
                wheel_url, wheel_sha = find_wheel_by_pattern(
                    pkg_data.get("wheels", []), WHEEL_ONLY.get(name, ""), python_tag
                )
                # Fallback to any arm64 wheel if none matched specifically
                if not wheel_url and pkg_data.get("wheels"):
                    wheel_url, wheel_sha = find_best_macosx_arm64_wheel(
                        pkg_data["wheels"], python_tag
                    )

                main_package = {
                    "name": name,
                    "version": pkg_data["version"],
                    "url": sdist_url,
                    "sha256": sdist_sha,
                    "wheel_url": wheel_url,
                    "wheel_sha": wheel_sha,
                }
            continue

        # Handle MLX
        if name in MLX_PACKAGES:
            mlx_data = resolve_mlx_from_lock(pkg_data)
            if mlx_data:
                resources.append({"name": name, "mlx": mlx_data})
            continue

        # Handle regular resources
        url, sha = None, None
        python_tag = f"cp{PY_VER.replace('.', '')}"

        if name in WHEEL_ONLY:
            url, sha = find_wheel_by_pattern(
                pkg_data.get("wheels", []), WHEEL_ONLY[name], python_tag
            )
            # Fallback for robustness
            if not url:
                url, sha = find_best_macosx_arm64_wheel(
                    pkg_data.get("wheels", []), python_tag
                )
        else:
            # Prefer sdist
            url = pkg_data.get("sdist", {}).get("url")
            sha = pkg_data.get("sdist", {}).get("hashes", {}).get("sha256")
            # Fallback to wheel
            if not url and pkg_data.get("wheels"):
                url, sha = find_best_macosx_arm64_wheel(pkg_data["wheels"], python_tag)

        if url:
            resources.append({"name": name, "url": url, "sha256": sha})

    if not main_package:
        print(f"Error: {proj_name} not found in input requirements", file=sys.stderr)
        return

    # Output Formula
    print(f"""class Calm < Formula
  include Language::Python::Virtualenv

  desc "Terminal-native CLI assistant backed by a local calmd daemon"
  homepage "https://github.com/quirkdom/calm"
  url "{main_package["url"]}"
  sha256 "{main_package["sha256"]}"
  license "MIT"

  depends_on arch: :arm64
  depends_on :macos
  depends_on "python@{PY_VER}"

  on_macos do""")

    for r in resources:
        if "mlx" in r:
            name = r["name"]
            data = r["mlx"]
            v26 = data.get("26")
            v15 = data.get("15")
            v14 = data.get("14")

            if v26 and v15 and v14:
                print(f"""
    resource "{name}" do
      if MacOS.version >= 26
        url "{v26[0]}"
        sha256 "{v26[1]}"
      elsif MacOS.version >= :sequoia
        url "{v15[0]}"
        sha256 "{v15[1]}"
      else
        url "{v14[0]}"
        sha256 "{v14[1]}"
      end
    end""")
        elif "url" in r and r["name"] in WHEEL_ONLY:
            print(f"""
    resource "{r["name"]}" do
      url "{r["url"]}"
      sha256 "{r["sha256"]}"
    end""")

    print(f"""
  end

  resource "{main_package["name"]}" do
    url "{main_package["wheel_url"]}"
    sha256 "{main_package["wheel_sha"]}"
  end""")

    for r in resources:
        if "url" in r and r["name"] not in WHEEL_ONLY:
            print(f"""
  resource "{r["name"]}" do
    url "{r["url"]}"
    sha256 "{r["sha256"]}"
  end""")

    print(f"""
  def install
    venv = virtualenv_create(libexec, "python{PY_VER}")

    resources.each do |r|
      next if r.name == "{main_package["name"]}"

      if r.url.end_with?(".whl")
        r.fetch
        wheel_name = File.basename(r.url.split("#").first)
        (buildpath/wheel_name).make_relative_symlink(r.cached_download)
        venv.pip_install buildpath/wheel_name
      else
        venv.pip_install r
      end
    end

    main_res = resource("{main_package["name"]}")
    main_res.fetch
    main_wheel = File.basename(main_res.url.split("#").first)
    (buildpath/main_wheel).make_relative_symlink(main_res.cached_download)
    venv.pip_install buildpath/main_wheel

    bin.install_symlink libexec/"bin/calm"
    bin.install_symlink libexec/"bin/calmd"
  end

  service do
    run [opt_bin/"calmd"]
    keep_alive false
    run_at_load true
    log_path var/"log/calmd.log"
    error_log_path var/"log/calmd.error.log"
  end

  test do
    assert_match "calm", shell_output("#{{bin}}/calm --help")
    assert_match "calmd", shell_output("#{{bin}}/calmd --help")
  end
end""")


if __name__ == "__main__":
    generate_formula()
