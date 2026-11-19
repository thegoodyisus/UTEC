"""Reglas de negocio de Bart: puntaje de consistencia de la boleta y evaluacion del producto (reglas R1 a R6).

Trabaja con items de DynamoDB (Decimal; los atributos vacios no vienen). Los valores de las reglas salen de las
tablas productos y ofertas_preaprobadas (versionadas), no del codigo, salvo los supuestos marcados abajo.
"""
import math

ORDEN_CALIF = ["NORMAL", "CPP", "DEFICIENTE", "DUDOSO", "PERDIDA"]
REDONDEO = 100  # el monto aprobable se redondea hacia abajo a multiplos de S/ 100

# --- Validacion de la boleta: checks y pesos del puntaje (pesos supuestos; suman 100) ---
UIT = 5500  # UIT 2026 (DS 301-2025-EF)
PESOS = {"C1_CUADRE_NETO": 40, "C2_SUMA_DESCUENTOS": 15, "C3_PENSION": 20, "C4_RENTA_5TA": 15, "C5_MONTOS_EN_TEXTO": 10}
TRAMOS_5TA = [(5, 0.08), (20, 0.14), (35, 0.17), (45, 0.20), (None, 0.30)]  # supuesto simplificado


def _f(x):
    return None if x is None or x == "" else float(x)


def factor(plazo, tea):
    r = (1 + tea) ** (1 / 12) - 1
    return r / (1 - (1 + r) ** -plazo)


def piso(x, paso=REDONDEO):
    return int(math.floor(x / paso) * paso) if x > 0 else 0


def renta_5ta_esperada(bruto):
    base = bruto * 14 - 7 * UIT
    impuesto, desde = 0.0, 0.0
    for tope, tasa in TRAMOS_5TA:
        hasta = tope * UIT if tope else float("inf")
        if base > desde:
            impuesto += (min(base, hasta) - desde) * tasa
        desde = hasta
    return max(impuesto, 0) / 12


def validar_campos(campos, montos_en_texto):
    """Devuelve (puntaje 0-100, checks, banderas). No decide: el umbral esta en productos.score_consistencia_min."""
    d = campos.get("descuentos") or {}
    bruto, neto, total = _f(campos.get("remuneracion_bruta")), _f(campos.get("neto_pagar")), _f(campos.get("total_descuentos"))
    partes = {k: _f(d.get(k)) or 0.0 for k in ("onp", "afp_aporte", "afp_comision", "afp_seguro", "renta_5ta", "otros")}
    suma = round(sum(partes.values()), 2)
    checks = []

    def check(cid, esperado, observado, tolerancia, ok):
        checks.append({"id": cid, "esperado": esperado, "observado": observado, "tolerancia": tolerancia,
                       "resultado": "OK" if ok else "FALLA"})

    completos = bruto is not None and neto is not None and total is not None
    check("C1_CUADRE_NETO", round(bruto - total, 2) if completos else None, neto, 1.0,
          completos and abs(bruto - total - neto) <= 1.0)
    check("C2_SUMA_DESCUENTOS", suma, total, 1.0, total is not None and abs(suma - total) <= 1.0)
    regimen = (campos.get("regimen_pension") or "").upper()
    if bruto and regimen == "ONP":
        ok = abs(partes["onp"] - 0.13 * bruto) <= 0.005 * bruto
        check("C3_PENSION", round(0.13 * bruto, 2), partes["onp"], round(0.005 * bruto, 2), ok)
    elif bruto and regimen == "AFP":
        ok = (abs(partes["afp_aporte"] - 0.10 * bruto) <= 0.005 * bruto
              and 0 < partes["afp_comision"] <= 0.025 * bruto and 0 < partes["afp_seguro"] <= 0.02 * bruto)
        check("C3_PENSION", round(0.10 * bruto, 2), partes["afp_aporte"], round(0.005 * bruto, 2), ok)
    else:
        check("C3_PENSION", "ONP o AFP", regimen or None, None, False)
    if bruto:
        esperada = renta_5ta_esperada(bruto)
        tol = max(50.0, 0.25 * esperada)
        check("C4_RENTA_5TA", round(esperada, 2), partes["renta_5ta"], round(tol, 2), abs(partes["renta_5ta"] - esperada) <= tol)
    else:
        check("C4_RENTA_5TA", None, partes["renta_5ta"], None, False)
    check("C5_MONTOS_EN_TEXTO", True, bool(montos_en_texto), None, bool(montos_en_texto))

    puntaje = sum(PESOS[c["id"]] for c in checks if c["resultado"] == "OK")
    banderas = [c["id"] for c in checks if c["resultado"] == "FALLA"]
    return puntaje, checks, banderas


# --- Evaluacion del producto elegido (R1-R6) ---
def evaluar(rcc, oferta, producto, neto, monto_solicitado):
    """Devuelve (estado, motivo, evaluacion, compra_deuda). Se detiene en la primera regla que no cumple."""
    pid = producto["producto_id"]
    tea = float(oferta["tea"])
    plazo = int(oferta["plazo_meses"]) if _f(oferta.get("plazo_meses")) else None  # el plazo es el de la oferta
    ratio_max = float(producto["ratio_endeud_max"])
    cuota_rcc = float(rcc["cuota_mensual_estimada"])
    monto_min = float(oferta["monto_minimo"])
    monto_max_oferta = float(oferta["monto_maximo"])
    neto = float(neto)
    monto_solicitado = float(monto_solicitado)
    reglas = []
    ev = {"ingreso_neto_validado": neto, "periodo_rcc": rcc["periodo"], "clasificacion_sbs": rcc["clasificacion_sbs"],
          "cuota_rcc_actual": round(cuota_rcc, 2), "ratio_endeud_max": ratio_max,
          "capacidad_mensual": None, "monto_aprobable": None, "monto_preaprobado": None,
          "cuota_mensual_estimada": None, "ratio_endeudamiento": None,
          "version_reglas": producto["version"], "reglas_evaluadas": reglas}
    cd = None

    def regla(rid, valor, umbral, cumple):
        reglas.append({"regla": rid, "valor": valor, "umbral": umbral, "cumple": cumple})
        return cumple

    if not regla("R1_CALIFICACION", rcc["clasificacion_sbs"], producto["calificacion_max"],
                 ORDEN_CALIF.index(rcc["clasificacion_sbs"]) <= ORDEN_CALIF.index(producto["calificacion_max"])):
        return "NO_ELEGIBLE", "CALIFICACION", ev, cd

    ingreso_min = float(producto["ingreso_neto_min"])
    if not regla("R2_INGRESO_MINIMO", neto, ingreso_min, neto >= ingreso_min):
        return "NO_ELEGIBLE", "INGRESO_INSUFICIENTE", ev, cd

    capacidad = round(neto * ratio_max - cuota_rcc, 2)
    ev["capacidad_mensual"] = capacidad
    if pid == "TC":
        pago_min = float(producto["pago_minimo_pct"])
        monto_cap = min(float(producto["multiplo_ingreso_max"]) * neto, capacidad / pago_min) if capacidad > 0 else 0
        cuota_de = lambda m: round(m * pago_min, 2)
    else:
        f = factor(plazo, tea)
        monto_cap = capacidad / f if capacidad > 0 else 0
        cuota_de = lambda m: round(m * f, 2)

    if pid == "COMPRA_DEUDA":
        comprables = [l for l in rcc.get("lineas", [])
                      if l["tipo_riesgo"] == "DIRECTO" and l["tipo_credito"] in ("CONSUMO", "TARJETA")]
        saldo_comprable = round(sum(float(l["saldo"]) for l in comprables), 2)
        cuota_comprable = round(sum(float(l["cuota_estimada"]) for l in comprables), 2)
        cd = {"saldo_comprable_actual": saldo_comprable, "cuota_actual_comprable": cuota_comprable}
        if not regla("R3_DEUDA_COMPRABLE", saldo_comprable, monto_min, saldo_comprable >= monto_min):
            return "NO_ELEGIBLE", "SIN_DEUDA_COMPRABLE", ev, cd
        monto_aprobable = piso(min(monto_cap, saldo_comprable, monto_max_oferta))
    else:
        monto_aprobable = piso(min(monto_cap, monto_max_oferta))
    ev["monto_aprobable"] = monto_aprobable

    if not regla("R4_CAPACIDAD", monto_aprobable, monto_min, monto_aprobable >= monto_min):
        return "NO_ELEGIBLE", "SIN_CAPACIDAD", ev, cd

    monto_eval = min(monto_solicitado, monto_aprobable)
    if pid == "COMPRA_DEUDA":
        cuota_nueva = cuota_de(monto_eval)
        cuota_reemplazada = round(cuota_comprable * monto_eval / saldo_comprable, 2)
        ahorro = round(cuota_reemplazada - cuota_nueva, 2)
        ahorro_pct = round(ahorro / cuota_reemplazada, 4) if cuota_reemplazada else 0
        cd.update({"monto_a_comprar": monto_eval, "cuota_reemplazada": cuota_reemplazada, "cuota_nueva": cuota_nueva,
                   "ahorro_mensual": ahorro, "ahorro_pct": ahorro_pct})
        if not regla("R5_AHORRO", ahorro_pct, float(producto["ahorro_min_pct"]),
                     ahorro_pct >= float(producto["ahorro_min_pct"])):
            return "NO_ELEGIBLE", "SIN_AHORRO", ev, cd

    if regla("R6_MONTO", monto_solicitado, monto_aprobable, monto_solicitado <= monto_aprobable):
        ev["monto_preaprobado"] = monto_solicitado
        ev["cuota_mensual_estimada"] = cuota_de(monto_solicitado)
        estado, motivo = "PRE_APROBADA", "DENTRO_DE_CAPACIDAD"
    else:
        ev["cuota_mensual_estimada"] = cuota_de(monto_aprobable)
        estado, motivo = "CONTRAOFERTA", "MONTO_SOBRE_CAPACIDAD"
    ev["ratio_endeudamiento"] = round((cuota_rcc + ev["cuota_mensual_estimada"]) / neto, 4)
    return estado, motivo, ev, cd
