#la documentacion html cubre todas las apis de negocio del contrato y omite lo del panel de resiliencia (decision 60)
import documentar


def test_cubre_todo_el_contrato_salvo_lo_omitido():
    doc = documentar.cargar()
    html = documentar.generar()
    for clave in documentar.operaciones(doc):
        presente = 'id="' + documentar.ancla(clave) + '"' in html
        assert presente == (clave not in documentar.OMITIR_OPERACIONES), clave


def test_no_menciona_el_monitoreo_del_panel():
    html = documentar.generar().lower()
    assert "trafico" not in html and "/demo/caer" not in html and "resiliencia" not in html


def test_es_determinista():
    assert documentar.generar() == documentar.generar()
