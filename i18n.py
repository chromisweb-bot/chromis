"""
i18n.py — Sistema de internacionalização (PT-BR / EN-US) do Chromis WEB.

Uso:
    from i18n import t, get_lang, set_lang
    t("login_title")  # retorna a string no idioma atual
"""

import streamlit as st

# ──────────────────────────────────────────────────────────────────────────
# Dicionário de traduções
# Estrutura: STRINGS[chave] = {"pt": "...", "en": "..."}
# ──────────────────────────────────────────────────────────────────────────

STRINGS = {
    # ===== Geral =====
    "app_name":            {"pt": "Chromis WEB",                 "en": "Chromis WEB"},
    "tagline":             {"pt": "Dosimetria com filmes radiocrômicos",
                            "en": "Radiochromic film dosimetry"},
    "continue":            {"pt": "Continuar",                   "en": "Continue"},
    "back":                {"pt": "Voltar",                      "en": "Back"},
    "save":                {"pt": "Salvar",                      "en": "Save"},
    "cancel":              {"pt": "Cancelar",                    "en": "Cancel"},
    "export":              {"pt": "Exportar",                    "en": "Export"},
    "calculate":           {"pt": "Calcular",                    "en": "Calculate"},
    "loading":             {"pt": "Carregando...",               "en": "Loading..."},
    "pending":             {"pt": "Pendente",                    "en": "Pending"},
    "waiting":             {"pt": "Aguardando",                  "en": "Waiting"},
    "done":                {"pt": "Concluído",                   "en": "Done"},
    "locked":              {"pt": "Bloqueado",                   "en": "Locked"},
    "approved":            {"pt": "APROVADO",                    "en": "PASS"},
    "failed":              {"pt": "REPROVADO",                   "en": "FAIL"},

    # ===== Login =====
    "login_title":         {"pt": "Entrar no sistema",           "en": "Sign in"},
    "login_subtitle":      {"pt": "Acesso para usuários autorizados",
                            "en": "For authorized users"},
    "login_user":          {"pt": "E-mail ou usuário",           "en": "Email or username"},
    "login_password":      {"pt": "Senha",                       "en": "Password"},
    "login_remember":      {"pt": "Lembrar-me",                  "en": "Remember me"},
    "login_forgot":        {"pt": "Esqueci a senha",             "en": "Forgot password"},
    "login_button":        {"pt": "Entrar no sistema",           "en": "Sign in"},
    "login_guest":         {"pt": "Continuar como visitante",    "en": "Continue as guest"},
    "login_or":            {"pt": "ou",                          "en": "or"},
    "login_footer":        {"pt": "Desenvolvido por MACIEL, J. O. · Python + Streamlit",
                            "en": "Developed by MACIEL, J. O. · Python + Streamlit"},

    # ===== Dashboard =====
    "dash_welcome":        {"pt": "Selecione um módulo de análise",
                            "en": "Select an analysis module"},
    "dash_setup_warn_title": {"pt": "Configure o estudo antes de começar",
                              "en": "Set up the study before starting"},
    "dash_setup_warn_desc":  {"pt": "O Setup alimenta o relatório e libera os módulos de análise",
                              "en": "Setup feeds the report and unlocks the analysis modules"},
    "dash_start_setup":    {"pt": "Iniciar Setup",               "en": "Start Setup"},
    "logout":              {"pt": "Sair",                        "en": "Logout"},

    # Grupos do dashboard
    "group_config":        {"pt": "Configuração",                "en": "Configuration"},
    "group_qa":            {"pt": "Controle de Qualidade",       "en": "Quality Control"},
    "group_dosimetry":     {"pt": "Análise Dosimétrica",         "en": "Dosimetric Analysis"},
    "group_output":        {"pt": "Saída",                       "en": "Output"},

    # ===== Módulos (nome + descrição) =====
    "mod_setup":           {"pt": "Setup do Estudo",             "en": "Study Setup"},
    "mod_setup_desc":      {"pt": "Máquina, energia, filme, scanner",
                            "en": "Machine, energy, film, scanner"},
    "mod_tps":             {"pt": "Planejamento do TPS",         "en": "TPS Plan"},
    "mod_tps_desc":        {"pt": "RT Dose, isodoses e pontos",  "en": "RT Dose, isodoses and points"},
    "mod_upload":          {"pt": "Upload de Imagens",           "en": "Image Upload"},
    "mod_upload_desc":     {"pt": "Filmes + pré-visualização",   "en": "Films + preview"},
    "mod_point":           {"pt": "Dose Pontual & Perfil",       "en": "Point Dose & Profile"},
    "mod_point_desc":      {"pt": "Comparação por coordenadas",  "en": "Comparison by coordinates"},
    "mod_symmetry":        {"pt": "Simetria de Bordas",          "en": "Edge Symmetry"},
    "mod_symmetry_desc":   {"pt": "Flatness, simetria, penumbra","en": "Flatness, symmetry, penumbra"},
    "mod_isocenter":       {"pt": "Isocentro Mecânico",          "en": "Mechanical Isocenter"},
    "mod_isocenter_desc":  {"pt": "Star shot · independente",    "en": "Star shot · standalone"},
    "mod_calibration":     {"pt": "Curva de Calibração",         "en": "Calibration Curve"},
    "mod_calibration_desc":{"pt": "Curva NOD × Dose",            "en": "NOD × Dose curve"},
    "mod_dosemap":         {"pt": "Mapa de Dose",                "en": "Dose Map"},
    "mod_dosemap_desc":    {"pt": "Distribuição 2D",             "en": "2D distribution"},
    "mod_isodose":         {"pt": "Mapa de Isodose",             "en": "Isodose Map"},
    "mod_isodose_desc":    {"pt": "Curvas filme vs TPS",         "en": "Film vs TPS curves"},
    "mod_gamma":           {"pt": "Análise Gamma",               "en": "Gamma Analysis"},
    "mod_gamma_desc":      {"pt": "Critérios TG-218",            "en": "TG-218 criteria"},
    "mod_report":          {"pt": "Relatório",                   "en": "Report"},
    "mod_report_desc":     {"pt": "Total ou parcial · PT/EN",    "en": "Full or partial · PT/EN"},

    # Dependências
    "requires_calib":      {"pt": "Requer calibração",           "en": "Requires calibration"},
    "requires_dosemap":    {"pt": "Requer mapa de dose",         "en": "Requires dose map"},
    "standalone_badge":    {"pt": "Independente",                "en": "Standalone"},

    # ===== Setup =====
    "setup_study_type":    {"pt": "Tipo de Estudo",              "en": "Study Type"},
    "setup_clinical":      {"pt": "Clínico",                     "en": "Clinical"},
    "setup_academic":      {"pt": "Acadêmico",                   "en": "Academic"},
    "setup_institution":   {"pt": "Instituição / Hospital",      "en": "Institution / Hospital"},
    "setup_university":    {"pt": "Universidade",                "en": "University"},
    "setup_responsible":   {"pt": "Responsável",                 "en": "Responsible"},
    "setup_machine_sec":   {"pt": "Acelerador / Feixe",          "en": "Accelerator / Beam"},
    "setup_machine":       {"pt": "Máquina",                     "en": "Machine"},
    "setup_manufacturer":  {"pt": "Fabricante",                  "en": "Manufacturer"},
    "setup_energy":        {"pt": "Energia",                     "en": "Energy"},
    "setup_field":         {"pt": "Campo (cm)",                  "en": "Field (cm)"},
    "setup_film_sec":      {"pt": "Filme Radiocrômico",          "en": "Radiochromic Film"},
    "setup_film_model":    {"pt": "Modelo",                      "en": "Model"},
    "setup_film_lot":      {"pt": "Lote",                        "en": "Lot"},
    "setup_scanner_sec":   {"pt": "Scanner",                     "en": "Scanner"},
    "setup_scanner_model": {"pt": "Marca / Modelo",              "en": "Brand / Model"},
    "setup_dpi":           {"pt": "DPI",                         "en": "DPI"},
    "setup_channel":       {"pt": "Canal de leitura",            "en": "Read channel"},
    "setup_channel_red":   {"pt": "Vermelho",                    "en": "Red"},
    "setup_channel_green": {"pt": "Verde",                       "en": "Green"},
    "setup_channel_blue":  {"pt": "Azul",                        "en": "Blue"},
    "setup_report_note":   {"pt": "Estes dados serão incluídos automaticamente no relatório final.",
                            "en": "This data will be automatically included in the final report."},
    "setup_save_draft":    {"pt": "Salvar rascunho",             "en": "Save draft"},
    "setup_save_continue": {"pt": "Salvar e continuar",          "en": "Save and continue"},

    # ===== Status bar / mensagens comuns =====
    "ready_for_analysis":  {"pt": "Pronto para as análises",     "en": "Ready for analysis"},
    "passing_rate":        {"pt": "Passing Rate",                "en": "Passing Rate"},
    "max_dose":            {"pt": "Dose máxima",                 "en": "Max dose"},
    "min_dose":            {"pt": "Dose mínima",                 "en": "Min dose"},
    "mean_dose":           {"pt": "Dose média",                  "en": "Mean dose"},
    "std_dev":             {"pt": "Desvio padrão",               "en": "Std deviation"},
    "mean_error":          {"pt": "Erro médio",                  "en": "Mean error"},
    "max_error":           {"pt": "Erro máximo",                 "en": "Max error"},
    "tolerance":           {"pt": "Tolerância",                  "en": "Tolerance"},

    # ===== Mensagens de bloqueio =====
    "module_locked_msg":   {"pt": "Este módulo está bloqueado. Complete os pré-requisitos primeiro.",
                            "en": "This module is locked. Complete the prerequisites first."},
    "wip_msg":             {"pt": "Módulo em construção — interface já disponível, cálculos em integração.",
                            "en": "Module under construction — interface ready, calculations being integrated."},

    # ===== Upload (deteccao de filmes) =====
    "up_params":          {"pt": "Parametros de analise", "en": "Analysis parameters"},
    "up_recoil":          {"pt": "Recuo da borda", "en": "Edge recoil"},
    "up_roi_size":        {"pt": "Tamanho do ROI", "en": "ROI size"},
    "up_roi_pct":         {"pt": "ROI (% area util)", "en": "ROI (% usable area)"},
    "up_dpi":             {"pt": "DPI do scan", "en": "Scan DPI"},
    "up_load_first":      {"pt": "Carregue um ou mais scans de filmes para iniciar a deteccao.",
                           "en": "Upload one or more film scans to start detection."},
    "up_n_detected":      {"pt": "filme(s) detectado(s) e ordenado(s) do mais claro (menor dose) ao mais escuro (maior dose).",
                           "en": "film(s) detected and ordered from lightest (lowest dose) to darkest (highest dose)."},
    "up_overview":        {"pt": "Visao geral", "en": "Overview"},
    "up_legend_film":     {"pt": "Filme", "en": "Film"},
    "up_legend_field":    {"pt": "Campo (se menor)", "en": "Field (if smaller)"},
    "up_legend_recoil":   {"pt": "Recuo da borda", "en": "Edge recoil"},
    "up_legend_roi":      {"pt": "ROI (medicao)", "en": "ROI (measurement)"},
    "up_individual":      {"pt": "Filmes individuais e doses", "en": "Individual films and doses"},
    "up_unit":            {"pt": "Unidade de dose", "en": "Dose unit"},
    "up_field_full":      {"pt": "campo do tamanho do filme", "en": "field same size as film"},
    "up_field_smaller":   {"pt": "campo menor que o filme", "en": "field smaller than film"},
    "up_mean_int":        {"pt": "Intensidade media", "en": "Mean intensity"},
    "up_dose_of":         {"pt": "Dose do filme", "en": "Dose of film"},
    "up_sel_curve":       {"pt": "Selecao para a curva de calibracao", "en": "Selection for calibration curve"},
    "up_sel_how":         {"pt": "Como selecionar os filmes:", "en": "How to select films:"},
    "up_sel_all":         {"pt": "Usar todos os filmes", "en": "Use all films"},
    "up_sel_group":       {"pt": "Escolher um grupo de filmes", "en": "Choose a group of films"},
    "up_sel_all_used":    {"pt": "Todos os filmes serao usados.", "en": "All films will be used."},
    "up_sel_mark":        {"pt": "Marque os filmes que deseja incluir na curva:",
                           "en": "Check the films to include in the curve:"},
    "up_sel_count":       {"pt": "filmes selecionados.", "en": "films selected."},
    "up_sel_one":         {"pt": "Selecione ao menos um filme.", "en": "Select at least one film."},

    # ===== Calibracao =====
    "cal_load_first":     {"pt": "Carregue os filmes na pagina de Upload de Imagens antes de calibrar.",
                           "en": "Upload films on the Image Upload page before calibrating."},
    "cal_go_upload":      {"pt": "Ir para Upload de Imagens", "en": "Go to Image Upload"},
    "cal_no_zero":        {"pt": "Nenhum filme com dose 0 foi encontrado. Para calcular o NOD, preciso do filme nao irradiado (background / dose zero).",
                           "en": "No film with dose 0 was found. To compute NOD, I need the unirradiated (background / zero dose) film."},
    "cal_no_fit":         {"pt": "Nao foi possivel ajustar nenhum modelo. Verifique os dados (precisa de ao menos 3 filmes com doses diferentes).",
                           "en": "Could not fit any model. Check the data (need at least 3 films with different doses)."},
    "cal_recommend":      {"pt": "Recomendacao: funcao", "en": "Recommendation: function"},
    "cal_why":            {"pt": "Por que essa recomendacao:", "en": "Why this recommendation:"},
    "cal_choose_model":   {"pt": "Escolha o modelo:", "en": "Choose the model:"},
    "cal_fit_r2":         {"pt": "R2 do ajuste", "en": "Fit R2"},
    "cal_see_points":     {"pt": "Ver pontos da curva (NOD x Dose)", "en": "See curve points (NOD x Dose)"},
    "cal_ready":          {"pt": "Curva pronta para o Mapa de Dose e o Relatorio",
                           "en": "Curve ready for Dose Map and Report"},
    "cal_save":           {"pt": "Salvar calibracao", "en": "Save calibration"},
    "cal_graph_theme":    {"pt": "Tema do grafico", "en": "Graph theme"},
    "cal_theme_dark":     {"pt": "Escuro", "en": "Dark"},
    "cal_theme_light":    {"pt": "Claro", "en": "Light"},
    "cal_points_measured":{"pt": "Pontos medidos", "en": "Measured points"},
    "cal_curve_fitted":   {"pt": "Curva ajustada", "en": "Fitted curve"},
    "cal_curve_title":    {"pt": "Curva de Calibracao", "en": "Calibration Curve"},
    "cal_nod_axis":       {"pt": "NOD (densidade optica liquida)", "en": "NOD (net optical density)"},

    # ===== Relatorio =====
    "rep_lang":           {"pt": "Idioma do relatorio", "en": "Report language"},
    "rep_type":           {"pt": "Tipo de relatorio", "en": "Report type"},
    "rep_full":           {"pt": "Relatorio Total (todos os modulos concluidos)",
                           "en": "Full report (all completed modules)"},
    "rep_including":      {"pt": "Incluindo:", "en": "Including:"},
    "rep_choose_mods":    {"pt": "Escolha os modulos para incluir:", "en": "Choose modules to include:"},
    "rep_available":      {"pt": "Modulos disponiveis", "en": "Available modules"},
    "rep_pending":        {"pt": "pendente", "en": "pending"},
    "rep_none_done":      {"pt": "Nenhum modulo concluido ainda. Complete ao menos o Setup, o Upload ou a Calibracao para gerar o relatorio.",
                           "en": "No module completed yet. Complete at least Setup, Upload or Calibration to generate the report."},
    "rep_generate":       {"pt": "Gerar relatorio PDF", "en": "Generate PDF report"},
    "rep_select_one":     {"pt": "Selecione ao menos um modulo.", "en": "Select at least one module."},
    "rep_generating":     {"pt": "Gerando PDF...", "en": "Generating PDF..."},
    "rep_generated":      {"pt": "Relatorio gerado!", "en": "Report generated!"},
    "rep_download":       {"pt": "Baixar PDF", "en": "Download PDF"},
    "up_field_label":     {"pt": "campo", "en": "field"},
    "rep_film_legend":    {"pt": "Parametros por filme", "en": "Per-film parameters"},
    "dm_need_calib":      {"pt": "Conclua a Calibracao antes de gerar o mapa de dose.",
                           "en": "Complete the Calibration before generating the dose map."},
    "dm_need_zero":       {"pt": "Mapa de dose requer o filme de dose zero (background).",
                           "en": "Dose map requires the zero-dose (background) film."},
    "dm_select_film":     {"pt": "Selecione o filme para o mapa de dose", "en": "Select the film for the dose map"},
    "dm_film":            {"pt": "Filme", "en": "Film"},
    "dm_dose_min":        {"pt": "Dose minima", "en": "Min dose"},
    "dm_dose_mean":       {"pt": "Dose media", "en": "Mean dose"},
    "dm_dose_max":        {"pt": "Dose maxima", "en": "Max dose"},
    "dm_source":          {"pt": "Origem do filme de medida", "en": "Measurement film source"},
    "dm_source_q":        {"pt": "De onde vem o filme a analisar?", "en": "Where does the film to analyze come from?"},
    "dm_source_upload":   {"pt": "Fazer upload de um filme especifico", "en": "Upload a specific film"},
    "dm_source_calib":    {"pt": "Usar os filmes da calibracao", "en": "Use the calibration films"},
    "dm_upload_hint":     {"pt": "Envie o filme irradiado com o campo/plano que deseja analisar.",
                           "en": "Upload the irradiated film with the field/plan you want to analyze."},
    "dm_upload":          {"pt": "Filme de medida", "en": "Measurement film"},
    "dm_no_calib_films":  {"pt": "Nenhum filme de calibracao carregado. Va ao Upload de Imagens.",
                           "en": "No calibration film loaded. Go to Image Upload."},
    "dm_waiting_film":    {"pt": "Aguardando o filme para gerar o mapa de dose.",
                           "en": "Waiting for the film to generate the dose map."},
    "dm_display":         {"pt": "Modo de exibicao", "en": "Display mode"},
    "dm_percent":         {"pt": "Dose percentual (%)", "en": "Percentage dose (%)"},
    "dm_absolute":        {"pt": "Dose absoluta", "en": "Absolute dose"},
    "dm_ref":             {"pt": "Referencia (100%)", "en": "Reference (100%)"},
    "dm_known_dose":      {"pt": "Dose irradiada no filme", "en": "Dose delivered to film"},
    "dm_known_dose_hint": {"pt": "Informe a dose com que o filme de medida foi irradiado (opcional, para validar o mapa).",
                           "en": "Enter the dose the measurement film was irradiated with (optional, to validate the map)."},
    "dm_validation":      {"pt": "Validacao (plato do campo irradiado)", "en": "Validation (irradiated field plateau)"},
    "dm_irradiated":      {"pt": "Dose irradiada", "en": "Delivered dose"},
    "dm_measured_center": {"pt": "Dose medida (plato)", "en": "Measured dose (plateau)"},
    "dm_difference":      {"pt": "Diferenca", "en": "Difference"},
    "dm_diff_hint":       {"pt": "Dose medida na regiao de dose plena (plato do campo), comparada a dose irradiada informada. Esperado: dentro de +/-3 a 5%.",
                           "en": "Dose measured in the full-dose region (field plateau), compared to the entered delivered dose. Expected: within +/-3 to 5%."},
}


def get_lang() -> str:
    """Retorna o idioma atual ('pt' ou 'en'). Default: pt."""
    return st.session_state.get("lang", "pt")


def set_lang(lang: str):
    """Define o idioma ('pt' ou 'en')."""
    if lang in ("pt", "en"):
        st.session_state["lang"] = lang


def t(key: str) -> str:
    """
    Retorna a tradução da chave no idioma atual.
    Se a chave não existir, retorna a própria chave (facilita debug).
    """
    lang = get_lang()
    entry = STRINGS.get(key)
    if entry is None:
        return key
    return entry.get(lang, entry.get("pt", key))
