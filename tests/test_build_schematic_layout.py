import pytest

from build_schematic_layout import _apply_affine, _fit_affine, _project, _solve_3x3


def test_solve_3x3_solves_a_known_system():
    # x + y + z = 6, 2y + 5z = -4, 2x + 5y - z = 27 -> x=5, y=3, z=-2 (textbook example)
    matrix = [[1, 1, 1], [0, 2, 5], [2, 5, -1]]
    vector = [6, -4, 27]
    x = _solve_3x3(matrix, vector)
    assert x == pytest.approx([5, 3, -2])


def test_fit_affine_recovers_an_exact_linear_transform():
    # schematic = 2*real_lat + 3*real_lng + 1 (both outputs, for simplicity)
    def transform(lat, lng):
        return (2 * lat + 3 * lng + 1, 2 * lat + 3 * lng + 1)

    reals = [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0), (2.0, 3.0)]
    pairs = [(r, transform(*r)) for r in reals]
    coeffs = _fit_affine(pairs)

    for real in reals:
        got = _apply_affine(coeffs, real)
        assert got == pytest.approx(transform(*real))


def test_apply_affine_identity_when_fit_on_identical_points():
    pairs = [((1.0, 2.0), (1.0, 2.0)), ((3.0, 4.0), (3.0, 4.0)), ((5.0, -1.0), (5.0, -1.0))]
    coeffs = _fit_affine(pairs)
    assert _apply_affine(coeffs, (10.0, 20.0)) == pytest.approx((10.0, 20.0))


def test_project_derives_height_from_content_aspect_ratio():
    # A 2-wide, 1-tall span (lng span 2, lat span 1) should come out twice as wide as tall.
    stations = {
        "A": {"*": (0.0, 0.0)},
        "B": {"*": (1.0, 2.0)},
    }
    projected, view_h = _project(stations)
    # view_w is the module constant (1000); height should be half that, plus padding
    # cancels out consistently since PAD is added on both axes -- just check the ratio
    # of the *content* (excluding padding) is 2:1.
    from build_schematic_layout import PAD, VIEW_W

    content_w = VIEW_W - 2 * PAD
    content_h = view_h - 2 * PAD
    assert content_w / content_h == pytest.approx(2.0)


def test_project_inverts_latitude_so_north_is_up():
    stations = {
        "South": {"*": (0.0, 0.0)},
        "North": {"*": (1.0, 0.0)},
    }
    projected, _view_h = _project(stations)
    # Higher latitude (north) must have a smaller y (further up the SVG canvas).
    assert projected["North"]["*"][1] < projected["South"]["*"][1]
