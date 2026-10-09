import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import calendar
import re
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Dashboard Executivo DF", layout="wide", page_icon="📊", initial_sidebar_state="expanded")

# --- CSS CUSTOMIZADO E CONFIGURAÇÃO PARA PDF ---
st.markdown("""
    <style>
    .stApp { background-color: #f4f4f9; }
    .metric-card { background-color: #222; color: white; padding: 20px; border-radius: 8px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 20px; }
    .metric-title { font-size: 16px; font-weight: bold; text-transform: uppercase; color: #fff; margin-bottom: 5px; }
    .metric-value { font-size: 32px; font-weight: bold; margin: 0; }
    .metric-sub { font-size: 11px; color: #aaa; margin-bottom: 10px; }
    .val-good { color: #4ade80; }
    .val-bad { color: #ff6b6b; }
    
    /* Configuração perfeita para quando o utilizador clica em "Gerar PDF" */
    @media print {
        header, .stSidebar, .stToolbar, footer { display: none !important; }
        .stApp { background-color: white !important; }
        .main { padding: 0 !important; margin: 0 !important; }
        .stTabs { page-break-inside: avoid; }
    }
    </style>
""", unsafe_allow_html=True)

# --- REGRAS DE OURO DA FROTA ---
ALLOWED_110S = ['CS19', 'CS20', 'CS21', 'CS22', 'CS24', 'CS25', 'CS26', 'CS27', 'CS28', 'CS29', 'CS30', 'CS31', 'CS36', 'CS37']
ALLOWED_130PRO = ['CS32', 'CS33', 'CS34', 'CS35']

# --- FUNÇÕES DE PROCESSAMENTO DE DADOS ---
@st.cache_data
def carregar_dados(uploaded_file):
    try:
        df = pd.read_excel(uploaded_file)
        
        # Limpeza agressiva e segura dos cabeçalhos
        def clean_header(col):
            c = str(col).strip().upper()
            c = re.sub(r'[\r\n]+', ' ', c) 
            c = re.sub('[\u200B-\u200D\uFEFF\xA0]', ' ', c) 
            c = re.sub(r'\s+', ' ', c).strip() 
            return c
            
        df.columns = [clean_header(c) for c in df.columns]
        
        colunas_necessarias = ['EQUIPAMENTO', 'DATA INÍCIO', 'TOTAL HORAS DECIMAIS']
        for col in colunas_necessarias:
            if col not in df.columns:
                st.error(f"Coluna obrigatória não encontrada: '{col}'. Colunas detetadas: {', '.join(df.columns)}")
                return None
                
        # Limpeza de Equipamentos
        df['EQUIPAMENTO'] = df['EQUIPAMENTO'].fillna('N/A').astype(str)
        df['EQUIPAMENTO'] = df['EQUIPAMENTO'].str.replace('[\u200B-\u200D\uFEFF\xA0]', ' ', regex=True)
        df['EQUIPAMENTO'] = df['EQUIPAMENTO'].str.replace(r'\s+', ' ', regex=True)
        df['EQUIPAMENTO'] = df['EQUIPAMENTO'].str.strip().str.upper()
        df = df[df['EQUIPAMENTO'] != 'CS18']
        
        # Definir Modelo
        if 'MODELO EQUIPAMENTO' in df.columns:
            df['MODELO'] = df['MODELO EQUIPAMENTO']
        elif 'MODELO' in df.columns: pass 
        else: df['MODELO'] = "N/A"
            
        df['MODELO'] = df['MODELO'].fillna('N/A').astype(str).str.strip().str.upper()
        
        def get_official_model(eqp, current_mod):
            if eqp in ALLOWED_110S: return 'SKT110S'
            if eqp in ALLOWED_130PRO: return 'SKT130PRO'
            return current_mod
            
        df['MODELO'] = df.apply(lambda row: get_official_model(row['EQUIPAMENTO'], row['MODELO']), axis=1)
        
        # Filtra a frota oficial
        df = df[~((df['MODELO'] == 'SKT110S') & (~df['EQUIPAMENTO'].isin(ALLOWED_110S)))]
        df = df[~((df['MODELO'] == 'SKT130PRO') & (~df['EQUIPAMENTO'].isin(ALLOWED_130PRO)))]

        # Processamento de Datas
        df['DATA_OBJ'] = pd.to_datetime(df['DATA INÍCIO'], errors='coerce')
        df = df.dropna(subset=['DATA_OBJ']).copy()
        
        df['diario'] = df['DATA_OBJ'].dt.strftime('%Y-%m-%d')
        df['mensal'] = df['DATA_OBJ'].dt.strftime('%m/%Y')
        df['semanal'] = df['DATA_OBJ'].apply(lambda x: f"Semana {x.isocalendar().week} - {x.isocalendar().year}")
        
        def preparar_coluna_texto(col_name, new_name):
            if col_name in df.columns:
                df[new_name] = df[col_name].fillna('N/A').astype(str).str.strip().str.upper()
            else:
                df[new_name] = 'N/A'
        
        preparar_coluna_texto('RESPONSABILIDADE NÍVEL 1', 'RESP1')
        preparar_coluna_texto('RESPONSABILIDADE NÍVEL 2', 'RESP2')
        preparar_coluna_texto('DETALHAMENTO', 'DETALHE')
        df['CAUSA'] = df['RESP1'] + " | " + df['RESP2'] + " | " + df['DETALHE']
        
        df['HORAS'] = pd.to_numeric(df['TOTAL HORAS DECIMAIS'], errors='coerce').fillna(0)
        
        return df
    except Exception as e:
        st.error(f"Erro crítico no ficheiro: {e}")
        return None

def calcular_horas_base(visao, periodos_array):
    horas = 0
    for p in periodos_array:
        if visao == 'diario': horas += 24
        elif visao == 'semanal': horas += 168
        elif visao == 'mensal':
            try:
                mes, ano = map(int, p.split('/'))
                horas += calendar.monthrange(ano, mes)[1] * 24
            except: pass
    return horas

def get_periodos_ordenados(df, view_type):
    p_unicos = df[view_type].dropna().unique()
    formatados = []
    for p in p_unicos:
        try:
            if view_type == 'diario':
                y, m, d = p.split('-')
                sort_val = int(f"{y}{m}{d}")
            elif view_type == 'mensal':
                m, y = p.split('/')
                sort_val = int(f"{y}{m}")
            elif view_type == 'semanal':
                parts = p.split(' - ')
                sort_val = int(f"{parts[1]}{int(parts[0].replace('Semana ', '')):02d}")
            formatados.append({'orig': p, 'sort': sort_val})
        except: pass
    formatados.sort(key=lambda x: x['sort'], reverse=True)
    return [x['orig'] for x in formatados], formatados

def get_periodos_limite(df, view_type, max_date, limite):
    todas_orig, todas_obj = get_periodos_ordenados(df, view_type)
    if not todas_orig: return []
    
    if view_type == 'diario': target = int(max_date.strftime('%Y%m%d'))
    elif view_type == 'mensal': target = int(max_date.strftime('%Y%m'))
    else: target = int(f"{max_date.isocalendar().year}{max_date.isocalendar().week:02d}")
        
    idx = next((i for i, obj in enumerate(todas_obj) if obj['sort'] <= target), 0)
    return todas_orig[idx : idx + limite][::-1] 

def formatar_intervalo_datas(view_type, max_date, limite):
    if view_type == 'diario':
        start_date = max_date - pd.Timedelta(days=limite-1)
        return f"{start_date.strftime('%d/%m/%Y')} a {max_date.strftime('%d/%m/%Y')}"
    elif view_type == 'semanal':
        start_date = max_date - pd.Timedelta(days=(limite*7)-1)
        return f"{start_date.strftime('%d/%m/%Y')} a {max_date.strftime('%d/%m/%Y')}"
    elif view_type == 'mensal':
        start_date = max_date - pd.DateOffset(months=limite-1)
        start_date = start_date.replace(day=1)
        end_date = max_date.replace(day=calendar.monthrange(max_date.year, max_date.month)[1])
        return f"{start_date.strftime('%d/%m/%Y')} a {end_date.strftime('%d/%m/%Y')}"

# --- CABEÇALHO ---
col_logo1, col_logo2 = st.columns([4, 1])
with col_logo1:
    st.title("📊 Dashboard Executivo DF")
with col_logo2:
    st.image("https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcT2y4RDy3dJMu1cyGiZwdmtHCopiNFuD2etAOmssdlvjO-k7JbJ9I_5LA&s=10", width=150)

# --- PAINEL DE CONTROLO NA SIDEBAR ---
st.sidebar.header("🛠️ Configurações e Filtros")

file_upload = st.sidebar.file_uploader("1. Ficheiro Excel", type=['xlsx', 'xls'])

if file_upload:
    df = carregar_dados(file_upload)
    
    if df is not None and not df.empty:
        visao = st.sidebar.selectbox("2. Visão", ['diario', 'semanal', 'mensal'], format_func=lambda x: x.capitalize())
        
        periodos_disp, _ = get_periodos_ordenados(df, visao)
        periodos_selecionados = st.sidebar.multiselect("3. Período(s)", periodos_disp, default=[periodos_disp[0]] if periodos_disp else [])
        
        modelos_disp = ["Todos os Modelos"] + sorted(df['MODELO'].unique())
        modelo_sel = st.sidebar.selectbox("4. Modelo", modelos_disp)
        
        meta_perc = st.sidebar.number_input("5. Meta (%)", min_value=0.0, max_value=100.0, value=90.0, step=1.0)
        meta_real = meta_perc / 100.0
        
        ordem_df = st.sidebar.selectbox("6. Ordem Gráfico", ['DF (Asc)', 'DF (Desc)', 'Eqp (A-Z)', 'Eqp (Z-A)'])
        
        st.sidebar.markdown("---")
        st.sidebar.markdown("**7. Evolução (Qtd. Analisada)**")
        c_d, c_s, c_m = st.sidebar.columns(3)
        qtd_dias = c_d.number_input("Dias", value=7, min_value=1)
        qtd_sem = c_s.number_input("Sem", value=4, min_value=1)
        qtd_mes = c_m.number_input("Mês", value=12, min_value=1)
        
        # Filtro Dinâmico de Equipamentos
        eqp_mapping = {eqp: mod for eqp, mod in zip(df['EQUIPAMENTO'], df['MODELO'])}
        for eqp in ALLOWED_110S: eqp_mapping[eqp] = 'SKT110S'
        for eqp in ALLOWED_130PRO: eqp_mapping[eqp] = 'SKT130PRO'
        
        eqps_ativos = sorted(list(set([e for e, m in eqp_mapping.items() if modelo_sel == "Todos os Modelos" or m == modelo_sel])))
        eqp_selecionados = st.sidebar.multiselect("8. Equipamentos (Análise)", eqps_ativos, default=eqps_ativos)

        # BOTÃO PARA GERAR PDF
        st.sidebar.markdown("---")
        pdf_button_html = """
        <button onclick="window.print()" style="background-color:#d32f2f; color:white; padding:12px; border:none; border-radius:6px; width:100%; cursor:pointer; font-weight:bold; font-size:14px; text-transform:uppercase;">
            📄 Exportar Relatório PDF
        </button>
        <p style="font-size:10px; color:#666; margin-top:5px; text-align:center;">Para formato A4, escolha a opção "Paisagem" na janela que abrir.</p>
        """
        st.sidebar.markdown(pdf_button_html, unsafe_allow_html=True)

# --- RENDERIZAÇÃO DA ABA ---
def renderizar_aba(titulo, periodos_analise, mostra_evolucao, limite_evolucao, tab_id, tipo_evolucao=None):
    st.markdown(f"## {titulo}")
    
    if not periodos_analise:
        st.info("Nenhum período válido para análise nesta aba.")
        return

    df_p = df[df[visao].isin(periodos_analise)].copy()
    max_date = df_p['DATA_OBJ'].max() if not df_p.empty else df['DATA_OBJ'].max()
    
    # 1. CARTÕES DE MODELO
    modelos_loop = sorted(list(set([eqp_mapping[e] for e in eqp_selecionados if e in eqp_mapping])))
    
    cols_cards = st.columns(max(len(modelos_loop), 1))
    for i, mod in enumerate(modelos_loop):
        eqps_do_mod = [e for e in eqp_selecionados if eqp_mapping.get(e) == mod]
        df_mod_periodo = df_p[df_p['EQUIPAMENTO'].isin(eqps_do_mod)]
        eqps_com_atividade = df_mod_periodo['EQUIPAMENTO'].unique()
        
        if len(eqps_com_atividade) == 0: continue
            
        h_base_total = calcular_horas_base(visao, periodos_analise) * len(eqps_com_atividade)
        h_parada = df_mod_periodo['HORAS'].sum()
        df_global = max(0, (h_base_total - h_parada) / h_base_total) * 100
        cls_color = "val-good" if df_global >= meta_perc else "val-bad"
        
        with cols_cards[i % len(cols_cards)]:
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">{mod}</div>
                <div class="metric-sub">DF Global do Período Analisado</div>
                <div class="metric-value {cls_color}">{df_global:.2f}%</div>
            </div>
            """, unsafe_allow_html=True)

    # 2. GRÁFICO DE EVOLUÇÃO
    if mostra_evolucao and len(modelos_loop) > 0 and tipo_evolucao:
        p_evol = get_periodos_limite(df, tipo_evolucao, max_date, limite_evolucao)
        
        dados_linha = []
        for mod in modelos_loop:
            eqps_do_mod = [e for e in eqp_selecionados if eqp_mapping.get(e) == mod]
            for p in p_evol:
                df_temp = df[(df[tipo_evolucao] == p) & (df['EQUIPAMENTO'].isin(eqps_do_mod))]
                eqps_ativos_temp = df_temp['EQUIPAMENTO'].unique()
                
                if len(eqps_ativos_temp) == 0: continue
                
                h_b = calcular_horas_base(tipo_evolucao, [p]) * len(eqps_ativos_temp)
                h_p = df_temp['HORAS'].sum()
                df_val = max(0, (h_b - h_p) / h_b) * 100
                dados_linha.append({'Período': p, 'Modelo': mod, 'DF': df_val})
                
        df_linha = pd.DataFrame(dados_linha).dropna()
        if not df_linha.empty:
            fig_lin = px.line(df_linha, x='Período', y='DF', color='Modelo', markers=True,
                              color_discrete_sequence=['#3b82f6', '#f59e0b', '#10b981', '#8b5cf6', '#06b6d4'])
            fig_lin.add_hline(y=meta_perc, line_dash="dash", line_color="#d32f2f", annotation_text=f"Meta {meta_perc}%")
            min_y = max(0, df_linha['DF'].min() - 5)
            if min_y > meta_perc: min_y = meta_perc - 5
            fig_lin.update_yaxes(range=[min_y, 105])
            fig_lin.update_layout(title=f"EVOLUÇÃO DO DF POR MODELO ({limite_evolucao} PERÍODOS)", template="plotly_white", margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig_lin, use_container_width=True, key=f"evol_{tab_id}")

    # 3. DADOS POR EQUIPAMENTO
    eqps_para_analise = eqp_selecionados
    if len(eqps_para_analise) == 0:
        st.info("Nenhum equipamento da frota foi selecionado.")
        return

    horas_base_eqp = calcular_horas_base(visao, periodos_analise)
    df_p_analise = df_p[df_p['EQUIPAMENTO'].isin(eqps_para_analise)]
    agrup_eqp = df_p_analise.groupby('EQUIPAMENTO')['HORAS'].sum().reset_index()
    
    df_todos_aptos = pd.DataFrame({'EQUIPAMENTO': eqps_para_analise})
    agrup_eqp = pd.merge(df_todos_aptos, agrup_eqp, on='EQUIPAMENTO', how='left').fillna(0)
    
    if horas_base_eqp > 0:
        agrup_eqp['DF'] = (horas_base_eqp - agrup_eqp['HORAS']) / horas_base_eqp
    else:
        agrup_eqp['DF'] = 0
        
    agrup_eqp['DF'] = agrup_eqp['DF'].apply(lambda x: max(0, x))
    agrup_eqp['DF_Perc'] = agrup_eqp['DF'] * 100
    agrup_eqp['Cor'] = agrup_eqp['DF_Perc'].apply(lambda x: '#555555' if x >= meta_perc else '#d32f2f')

    if ordem_df == 'DF (Asc)': agrup_eqp = agrup_eqp.sort_values(['DF_Perc', 'EQUIPAMENTO'], ascending=[True, True])
    elif ordem_df == 'DF (Desc)': agrup_eqp = agrup_eqp.sort_values(['DF_Perc', 'EQUIPAMENTO'], ascending=[False, True])
    elif ordem_df == 'Eqp (A-Z)': agrup_eqp = agrup_eqp.sort_values('EQUIPAMENTO', ascending=True)
    else: agrup_eqp = agrup_eqp.sort_values('EQUIPAMENTO', ascending=False)

    fig_bar = go.Figure()
    fig_bar.add_trace(go.Bar(
        x=agrup_eqp['EQUIPAMENTO'], y=agrup_eqp['DF_Perc'], marker_color=agrup_eqp['Cor'],
        text=agrup_eqp['DF_Perc'].apply(lambda x: f"{x:.0f}%"), textposition='auto'
    ))
    fig_bar.add_hline(y=meta_perc, line_dash="dash", line_color="#d32f2f", annotation_text=f"Meta {meta_perc}%")
    min_bar_y = max(0, agrup_eqp['DF_Perc'].min() - 5)
    if min_bar_y > meta_perc: min_bar_y = meta_perc - 5
    fig_bar.update_layout(title="DF POR EQUIPAMENTO (%)", template="plotly_white", margin=dict(t=40, b=0, l=0, r=0))
    fig_bar.update_yaxes(range=[min_bar_y, 105])
    st.plotly_chart(fig_bar, use_container_width=True, key=f"bar_eqp_{tab_id}")

    # 4. GRÁFICOS DE CAUSA
    c_c1, c_c2 = st.columns(2)
    with c_c1:
        agrup_r1 = df_p_analise.groupby('RESP1')['HORAS'].sum().reset_index()
        if not agrup_r1.empty and agrup_r1['HORAS'].sum() > 0:
            fig_r1 = px.pie(agrup_r1, names='RESP1', values='HORAS', hole=0.5, title="HORAS PARADAS POR RESP. NÍVEL 1", color_discrete_sequence=['#111', '#444', '#777', '#aaa'])
            fig_r1.update_traces(textinfo='percent+value')
            fig_r1.update_layout(margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig_r1, use_container_width=True, key=f"pie_r1_{tab_id}")

    with c_c2:
        agrup_r2 = df_p_analise.groupby('RESP2')['HORAS'].sum().nlargest(10).reset_index().sort_values('HORAS', ascending=True)
        if not agrup_r2.empty and agrup_r2['HORAS'].sum() > 0:
            fig_r2 = px.bar(agrup_r2, x='HORAS', y='RESP2', orientation='h', title="ACUMULADO: RESP. NÍVEL 2 (TOP 10)", color_discrete_sequence=['#444'])
            fig_r2.update_layout(template="plotly_white", margin=dict(t=40, b=0, l=0, r=0), yaxis_title="")
            st.plotly_chart(fig_r2, use_container_width=True, key=f"bar_r2_{tab_id}")

    agrup_det = df_p_analise.groupby('DETALHE')['HORAS'].sum().nlargest(10).reset_index().sort_values('HORAS', ascending=True)
    if not agrup_det.empty and agrup_det['HORAS'].sum() > 0:
        agrup_det['DETALHE'] = agrup_det['DETALHE'].apply(lambda x: x[:40]+'...' if len(x)>40 else x)
        fig_det = px.bar(agrup_det, x='HORAS', y='DETALHE', orientation='h', title="ACUMULADO: DETALHAMENTO (TOP 10)", color_discrete_sequence=['#444'])
        fig_det.update_layout(template="plotly_white", margin=dict(t=40, b=0, l=0, r=0), yaxis_title="")
        st.plotly_chart(fig_det, use_container_width=True, key=f"bar_det_{tab_id}")

    # 5. TABELA EM HTML PURO COM CONCATENAÇÃO EM LINHA (RESOLVE RENDERIZAÇÃO E CORTES)
    st.markdown("### 🔻 PRINCIPAIS CONTRIBUINTES: EQUIPAMENTOS ABAIXO DA META")
    abaixo_meta = agrup_eqp[agrup_eqp['DF_Perc'] < meta_perc].copy()
    
    if abaixo_meta.empty:
        st.success("🎉 Excelente! Nenhum equipamento selecionado ficou abaixo da meta neste período.")
    else:
        # Construção do HTML em linha contínua sem formatação de parágrafos/espaços para evitar bugs de markdown
        tabela_html = "<table style='width:100%; border-collapse: collapse; font-family: sans-serif; font-size: 13px; background-color: white; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1);'>"
        tabela_html += "<thead><tr style='background-color: #222; color: white; text-align: left;'>"
        tabela_html += "<th style='padding: 12px; border: 1px solid #ddd;'>Equipamento</th>"
        tabela_html += "<th style='padding: 12px; border: 1px solid #ddd;'>Meta DF</th>"
        tabela_html += "<th style='padding: 12px; border: 1px solid #ddd;'>DF Calculado</th>"
        tabela_html += "<th style='padding: 12px; border: 1px solid #ddd;'>Diferença</th>"
        tabela_html += "<th style='padding: 12px; border: 1px solid #ddd; width: 50%;'>Principais Fatores Contribuintes</th>"
        tabela_html += "</tr></thead><tbody>"
        
        for _, row in abaixo_meta.iterrows():
            eqp = row['EQUIPAMENTO']
            df_calc = row['DF_Perc']
            dif = meta_perc - df_calc
            tot_horas = row['HORAS']
            
            causas_eqp = df_p_analise[df_p_analise['EQUIPAMENTO'] == eqp].groupby('CAUSA')['HORAS'].sum().nlargest(5)
            
            causas_html = f"<div style='margin-bottom:5px; padding-bottom:5px; border-bottom:1px dashed #ccc;'><b>Total Horas Acumuladas no Período:</b> <span style='color:#d32f2f; font-weight:bold;'>{tot_horas:.2f}h</span></div>"
            for causa, hrs in causas_eqp.items():
                perc = (hrs / tot_horas) * 100 if tot_horas > 0 else 0
                causas_html += f"&bull; <b>{causa}</b> <span style='color:#666;'>[{hrs:.2f}h &rarr; <b>{perc:.1f}%</b>]</span><br>"
            
            tabela_html += "<tr>"
            tabela_html += f"<td style='padding: 12px; border: 1px solid #ddd; font-weight:bold;'>{eqp}</td>"
            tabela_html += f"<td style='padding: 12px; border: 1px solid #ddd;'>{meta_perc:.2f}%</td>"
            tabela_html += f"<td style='padding: 12px; border: 1px solid #ddd; color: #d32f2f; font-weight:bold;'>{df_calc:.2f}%</td>"
            tabela_html += f"<td style='padding: 12px; border: 1px solid #ddd; color: #d32f2f; font-weight:bold;'>-{dif:.2f}%</td>"
            tabela_html += f"<td style='padding: 12px; border: 1px solid #ddd; white-space: pre-wrap; line-height: 1.5;'>{causas_html}</td>"
            tabela_html += "</tr>"
            
        tabela_html += "</tbody></table>"
        st.markdown(tabela_html, unsafe_allow_html=True)


# --- INÍCIO DA RENDERIZAÇÃO DAS ABAS ---
if file_upload and 'df' in locals() and df is not None and len(periodos_selecionados) > 0 and len(eqp_selecionados) > 0:
    
    max_date_geral = df[df[visao].isin(periodos_selecionados)]['DATA_OBJ'].max() if not df[df[visao].isin(periodos_selecionados)].empty else df['DATA_OBJ'].max()
    
    tab1, tab2, tab3, tab4 = st.tabs(["Dashboard Principal", "Acumulado Diário", "Acumulado Semanal", "Acumulado Mensal"])
    
    with tab1:
        desc = periodos_selecionados[0] if len(periodos_selecionados)==1 else f"{len(periodos_selecionados)} Períodos Selecionados"
        renderizar_aba(
            titulo=f"Visão: {visao.capitalize()} | Períodos: {desc}",
            periodos_analise=periodos_selecionados, mostra_evolucao=False, limite_evolucao=0, tab_id="prin"
        )
        
    with tab2:
        p_dia = get_periodos_limite(df, 'diario', max_date_geral, qtd_dias)
        intervalo = formatar_intervalo_datas('diario', max_date_geral, qtd_dias)
        renderizar_aba(
            titulo=f"Acumulado Diário (Últimos {qtd_dias} Dias | {intervalo})",
            periodos_analise=p_dia, mostra_evolucao=True, limite_evolucao=qtd_dias, tab_id="dia", tipo_evolucao='diario'
        )
        
    with tab3:
        p_sem = get_periodos_limite(df, 'semanal', max_date_geral, qtd_sem)
        intervalo = formatar_intervalo_datas('semanal', max_date_geral, qtd_sem)
        renderizar_aba(
            titulo=f"Acumulado Semanal (Últimas {qtd_sem} Semanas | {intervalo})",
            periodos_analise=p_sem, mostra_evolucao=True, limite_evolucao=qtd_sem, tab_id="sem", tipo_evolucao='semanal'
        )
        
    with tab4:
        p_mes = get_periodos_limite(df, 'mensal', max_date_geral, qtd_mes)
        intervalo = formatar_intervalo_datas('mensal', max_date_geral, qtd_mes)
        renderizar_aba(
            titulo=f"Acumulado Mensal (Últimos {qtd_mes} Meses | {intervalo})",
            periodos_analise=p_mes, mostra_evolucao=True, limite_evolucao=qtd_mes, tab_id="mes", tipo_evolucao='mensal'
        )
