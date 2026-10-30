from mothlit.ui import brand


def test_svg_becomes_polygons():
    polygons, side = brand._polygons()
    assert side == 512
    assert len(polygons) == 3  # body + two antenna details
    assert len(polygons[0]) > 50


def test_image_has_content_and_right_size():
    img = brand.image(32)
    assert img.size == (32, 32)
    assert img.getbbox() is not None


def test_tray_fills_the_whole_width():
    for size in (16, 24, 32):
        left, _, right, _ = brand.tray_image(size).getbbox()
        assert (left, right) == (0, size)  # touching the edges: the most that fits


def test_tray_ico_has_every_size(tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.setenv("APPDATA", str(tmp_path))
    ico = Image.open(brand.tray_ico())
    assert sorted(ico.info["sizes"]) == [(s, s) for s in brand.TRAY_SIZES]


def test_tray_ico_works_in_the_executable(tmp_path, monkeypatch):
    # In the PyInstaller .exe the modules do not exist as files: it cannot depend on __file__.
    monkeypatch.setenv("APPDATA", str(tmp_path))
    brand.tray_ico()  # the 1st launch creates the .ico; the bug showed up from the 2nd one on
    monkeypatch.setattr(brand, "__file__", str(tmp_path / "_internal" / "does_not_exist" / "brand.pyc"))
    assert brand.tray_ico().exists()


def test_ico_built_in_the_config_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    path = brand.ico_file()
    assert path == tmp_path / "Mothlit" / "mothlit.ico"
    assert path.stat().st_size > 0
