"""Generate native safety-test constants from the canonical Python cases."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests/fixtures"))
from cases import ONE_BUILDING


def main():
    c = ONE_BUILDING
    g, w, b, p = c.grid, c.wind, c.buildings[0], c.parameterizations
    lines = ["#pragma once", "namespace fixture {"]
    for name, value in {
        "nx": g.nx, "ny": g.ny, "nz": g.nz,
        "max_iterations": c.solver.max_iterations,
    }.items():
        lines.append(f"inline constexpr int {name} = {value};")
    for name, value in {
        "cell_size": g.cell_size, "speed": w.speed, "direction": w.direction,
        "reference_height": w.reference_height, "roughness": w.roughness_length,
        "sensor_x": w.sensor_x, "sensor_y": w.sensor_y,
        "tolerance": c.solver.tolerance, "height": b.height,
        "base_height": b.base_height, "wall_roughness": p.wall_roughness,
    }.items():
        lines.append(f"inline constexpr float {name} = {value!r}f;")
    for name in ["rooftop_flag", "upwind_cavity_flag", "street_canyon_flag",
                 "street_intersection_flag", "wake_flag", "high_rise_flag", "sidewall_flag"]:
        lines.append(f"inline constexpr int {name} = {getattr(p, name)};")
    lines.append(f'inline constexpr const char *timestamp = "{w.timestamp}";')
    ring = (*b.vertices, b.vertices[0])
    vertices = ", ".join("{" + f"{x!r}f, {y!r}f" + "}" for x, y in ring)
    lines.append(f"inline constexpr float vertices[][2] = {{{vertices}}};")
    lines.append("}")
    Path(sys.argv[1]).write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
