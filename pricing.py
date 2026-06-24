"""Central pricing rules for stonework quote items."""

CUBA_VALORES_PADRAO = {
    "Embutida": 225,
    "Sobreposta": 125,
    "Esculpida": 175,
    "Tradicional Inox": 225,
    "Tanque Inox": 500,
    "Apoio Cliente": 125,
    "Embutida Cliente": 125,
    "Gourmet Cliente": 225,
    "Sobrepor Cliente": 125,
    "Tanque Inox Cliente": 225,
}

COOKTOP_VALOR_PADRAO = 50
NICHO_MAO_OBRA_PADRAO = 150
MINIMO_MEDIDA_CM = 10


def _float(valor, padrao=0.0):
    try:
        return float(valor or padrao)
    except (TypeError, ValueError):
        return padrao


def _int(valor, padrao=0):
    try:
        return int(valor or padrao)
    except (TypeError, ValueError):
        return padrao


def medida_minima(valor, minimo=MINIMO_MEDIDA_CM):
    valor = _float(valor)
    minimo = _float(minimo, MINIMO_MEDIDA_CM)
    return minimo if 0 < valor < minimo else valor


def aplicar_margem_material(
    tipo_produto,
    valor_material,
    valor_base,
    pedra_simples_margem=0,
    soleira_margem=0,
    ilharga_margem=0,
    margem_ate_1000=30,
    margem_ate_2000=15,
    margem_acima_2000=10,
    margem_ilharga_bipolida=15,
    pedra_simples_com_saia_margem=0,
    pedra_bipolida_com_saia_margem=15,
    pedra_bipolida_margem=15,
):
    if tipo_produto == "Pedra Simples":
        return valor_base * (1 + _float(pedra_simples_margem) / 100)

    if tipo_produto == "Soleira":
        margem = soleira_margem if _float(soleira_margem) else pedra_simples_margem
        return valor_base * (1 + _float(margem) / 100)

    if tipo_produto == "Ilharga":
        return valor_base * (1 + _float(ilharga_margem) / 100)

    if tipo_produto == "Pedra Simples com Saia":
        return valor_base * (1 + _float(pedra_simples_com_saia_margem) / 100)

    if tipo_produto in ["Bancada", "Lavatorio"]:
        if valor_material < 1000:
            return valor_base * (1 + _float(margem_ate_1000) / 100)
        if valor_material < 2000:
            return valor_base * (1 + _float(margem_ate_2000) / 100)
        if valor_material < 1000000:
            return valor_base * (1 + _float(margem_acima_2000) / 100)

    if tipo_produto == "Ilharga Bipolida" and valor_base < 1000000:
        return valor_base * (1 + _float(margem_ilharga_bipolida) / 100)

    if tipo_produto == "Pedra Bipolida com Saia" and valor_base < 1000000:
        return valor_base * (1 + _float(pedra_bipolida_com_saia_margem) / 100)

    if tipo_produto == "Pedra Bipolida" and valor_base < 1000000:
        return valor_base * (1 + _float(pedra_bipolida_margem) / 100)

    return valor_base


def calcular_area_nicho(
    comprimento,
    largura,
    profundidade_nicho,
    tem_fundo,
    tem_alisar,
    largura_alisar,
    minimo_medida_cm=MINIMO_MEDIDA_CM,
    nicho_folga_cm=4,
    alisar_margem=0,
):
    comprimento_cal = medida_minima(comprimento, minimo_medida_cm)
    largura_cal = medida_minima(largura, minimo_medida_cm)
    profundidade_cal = medida_minima(profundidade_nicho, minimo_medida_cm)
    folga = _float(nicho_folga_cm, 4)

    if tem_fundo == "Sim":
        area = (
            ((comprimento_cal + folga) * (largura_cal + folga))
            + (((comprimento_cal + folga) * profundidade_cal) * 2)
            + (((largura_cal + folga) * profundidade_cal) * 2)
        )
    else:
        area = ((comprimento_cal + folga) + (largura_cal + folga)) * profundidade_cal * 2

    if tem_alisar == "Sim" and _float(largura_alisar) > 0:
        largura_alisar_cal = medida_minima(largura_alisar, minimo_medida_cm)
        area_alisar = ((comprimento_cal + (largura_alisar_cal * 2)) * largura_alisar_cal * 2) + (
            (largura_cal + (largura_alisar_cal * 2)) * largura_alisar_cal * 2
        )
        area += area_alisar * (1 + _float(alisar_margem) / 100)

    return area


def calcular_area_cuba_esculpida(modelo_cuba, comprimento_cuba, largura_cuba, profundidade_cuba):
    comprimento_cuba = _float(comprimento_cuba)
    largura_cuba = _float(largura_cuba)
    profundidade_cuba = _float(profundidade_cuba)

    if modelo_cuba == "Prainha":
        return ((comprimento_cuba * largura_cuba) + (largura_cuba * 2) * profundidade_cuba) / 10000

    return (
        (comprimento_cuba * largura_cuba * 2)
        + (comprimento_cuba * 2 + largura_cuba * 2) * profundidade_cuba
    ) / 10000


def calcular_valor_item(
    *,
    tipo_produto,
    valor_material,
    quantidade=1,
    comprimento=0,
    largura=0,
    comprimento_saia=0,
    largura_saia=0,
    comprimento_fronte=0,
    largura_fronte=0,
    tipo_cuba="",
    quantidade_cubas=0,
    comprimento_cuba=0,
    largura_cuba=0,
    profundidade_cuba=0,
    modelo_cuba="Normal",
    tem_cooktop="Nao",
    acessorios_valor_total=0,
    instalacao="Nao",
    instalacao_valor=0,
    rt="Nao",
    rt_percentual=0,
    profundidade_nicho=0,
    tem_fundo="Nao",
    tem_alisar="Nao",
    largura_alisar=0,
    cuba_valores=None,
    cooktop_valor=COOKTOP_VALOR_PADRAO,
    nicho_mao_obra=NICHO_MAO_OBRA_PADRAO,
    nicho_sem_fundo_mao_obra=None,
    minimo_medida_cm=MINIMO_MEDIDA_CM,
    pedra_simples_margem=0,
    soleira_margem=0,
    ilharga_margem=0,
    bancada_margem_ate_1000=30,
    bancada_margem_ate_2000=15,
    bancada_margem_acima_2000=10,
    ilharga_bipolida_margem=15,
    pedra_simples_com_saia_margem=0,
    pedra_bipolida_com_saia_margem=15,
    pedra_bipolida_margem=15,
    pedra_box_adicional=30,
    nicho_folga_cm=4,
    saia_margem=0,
    fronte_margem=0,
    alisar_margem=0,
):
    valor_material = _float(valor_material)
    quantidade = max(_int(quantidade, 1), 1)
    cuba_valores = cuba_valores or CUBA_VALORES_PADRAO

    minimo_medida_cm = _float(minimo_medida_cm, MINIMO_MEDIDA_CM)
    comprimento_cal = max(_float(comprimento), minimo_medida_cm)
    largura_cal = max(_float(largura), minimo_medida_cm)
    valor_base = valor_material * (comprimento_cal * largura_cal / 10000)
    valor_base = aplicar_margem_material(
        tipo_produto,
        valor_material,
        valor_base,
        pedra_simples_margem,
        soleira_margem,
        ilharga_margem,
        bancada_margem_ate_1000,
        bancada_margem_ate_2000,
        bancada_margem_acima_2000,
        ilharga_bipolida_margem,
        pedra_simples_com_saia_margem,
        pedra_bipolida_com_saia_margem,
        pedra_bipolida_margem,
    )

    total = valor_base

    if tipo_produto == "Nicho":
        area_nicho = calcular_area_nicho(
            comprimento,
            largura,
            profundidade_nicho,
            tem_fundo,
            tem_alisar,
            largura_alisar,
            minimo_medida_cm,
            nicho_folga_cm,
            alisar_margem,
        )
        mao_obra_nicho = nicho_mao_obra
        if tem_fundo != "Sim" and nicho_sem_fundo_mao_obra is not None:
            mao_obra_nicho = nicho_sem_fundo_mao_obra
        total = (area_nicho / 10000) * valor_material + _float(mao_obra_nicho, NICHO_MAO_OBRA_PADRAO)

    if tipo_produto in ["Ilharga", "Ilharga Bipolida", "Pedra Simples com Saia", "Pedra Bipolida com Saia", "Bancada", "Lavatorio"]:
        total += (_float(comprimento_saia) / 100) * _float(saia_margem)

    if tipo_produto in ["Bancada", "Lavatorio"]:
        total += (_float(comprimento_fronte) / 100) * _float(fronte_margem)

    if tipo_produto == "Pedra de Box":
        total = valor_base + _float(pedra_box_adicional, 30)

    if tipo_cuba:
        qtd_cubas = _int(quantidade_cubas, 0)
        if tipo_cuba == "Esculpida":
            qtd_esculpida = max(qtd_cubas, 1)
            total += cuba_valores.get(tipo_cuba, 0) * qtd_esculpida
            area_cuba = calcular_area_cuba_esculpida(
                modelo_cuba,
                comprimento_cuba,
                largura_cuba,
                profundidade_cuba,
            )
            total += area_cuba * valor_material * qtd_esculpida
        else:
            total += cuba_valores.get(tipo_cuba, 0) * qtd_cubas

    total += _float(acessorios_valor_total)
    if tem_cooktop == "Sim" and _float(acessorios_valor_total) <= 0:
        total += _float(cooktop_valor)

    if instalacao == "Sim":
        total += _float(instalacao_valor)

    total *= quantidade

    rt_percentual = _float(rt_percentual)
    if rt == "Sim" and rt_percentual > 0:
        total = total / (1 - rt_percentual / 100)

    return round(total, 2)
