import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import calendar
from datetime import datetime

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Dashboard DF", layout="wide", page_icon="📊")

# --- CSS CUSTOMIZADO (Para manter o visual profissional corporativo) ---
st.markdown("""
    <style>
    .stApp { background-color: #e8e8e8; }
    .card { background-color: #222; color: white; padding: 20px; border-radius: 8px; text-align: center; box-shadow: 0 4px 6px rgba(0,0,0,0.1); margin-bottom: 20px;}
    .card-title { font-size: 16px; font-weight: bold; text-transform: uppercase; color: #fff; margin-bottom: 5px; }
    .card-value { font-size: 32px; font-weight: bold; margin: 0; }
    .good { color: #4ade80; }
    .bad { color: #ff6b6b; }
    .metric-subtitle { font-size: 12px; color: #888; }
    </style>
""", unsafe_allow_html=True)

# --- FUNÇÕES DE PROCESSAMENTO ---
@st.cache_data
def carregar_dados(uploaded_file):
    try:
        # Lê o Excel
        df = pd.read_excel(uploaded_file)
        
        # Padroniza colunas
        df.columns = [str(c).strip().upper() for c in df.columns]
        
        # Verifica colunas essenciais
        colunas_necessarias = ['EQUIPAMENTO', 'DATA INÍCIO', 'TOTAL HORAS DECIMAIS']
        for col in colunas_necessarias:
            if col not in df.columns:
                st.error(f"Coluna obrigatória não encontrada: {col}")
                return None
                
        # Limpeza de strings (Espaços invisíveis, etc)
        df['EQUIPAMENTO'] = df['EQUIPAMENTO'].astype(str).replace(r'[\u200B-\u200D\uFEFF\xA0]', ' ', regex=True).replace(r'\s+', ' ', regex=True).str.strip().str.upper()
        
        # Filtra CS18
        df = df[df['EQUIPAMENTO'] != 'CS18']
        
        # Define o Modelo
        if 'MODELO EQUIPAMENTO' in df.columns:
            df['MODELO'] = df['MODELO EQUIPAMENTO']
        elif 'MODELO' in df.columns:
            pass # já existe
        else:
            df['MODELO'] = "N/A"
            
        df['MODELO'] = df['MODELO'].astype(str).str.strip().str.upper()
        
        # Processamento de Datas
        df['DATA INÍCIO'] = pd.to_datetime(df['DATA INÍCIO'], errors='coerce')
        df = df.dropna(subset=['DATA INÍCIO'])
        
        # Criar Períodos
        df['ANO'] = df['DATA INÍCIO'].dt.year
        df['MES'] = df['DATA INÍCIO'].dt.month
        df['DIA'] = df['DATA INÍCIO'].dt.day
        
        df['diario'] = df['DATA INÍCIO'].dt.strftime('%Y-%m-%d')
        df['mensal'] = df['DATA INÍCIO'].dt.strftime('%m/%Y')
        
        # Lógica de Semana (ISO)
        df['semanal'] = df['DATA INÍCIO'].apply(lambda x: f"Semana {x.isocalendar()[1]} - {x.isocalendar()[0]}")
        
        # Tratar Valores Nulos de Responsabilidade
        df['RESPONSABILIDADE NÍVEL 1'] = df.get('RESPONSABILIDADE NÍVEL 1', 'N/A').fillna('N/A').astype(str)
        df['RESPONSABILIDADE NÍVEL 2'] = df.get('RESPONSABILIDADE NÍVEL 2', 'N/A').fillna('N/A').astype(str)
        df['DETALHAMENTO'] = df.get('DETALHAMENTO', 'N/A').fillna('N/A').astype(str)
        df['CAUSA'] = df['RESPONSABILIDADE NÍVEL 1'] + " | " + df['RESPONSABILIDADE NÍVEL 2'] + " | " + df['DETALHAMENTO']
        
        # Horas
        df['TOTAL HORAS DECIMAIS'] = pd.to_numeric(df['TOTAL HORAS DECIMAIS'], errors='coerce').fillna(0)
        
        return df
    except Exception as e:
        st.error(f"Erro ao ler o ficheiro: {e}")
        return None

def calcular_horas_base(visao, periodos):
    horas = 0
    for p in periodos:
        if visao == 'diario':
            horas += 24
        elif visao == 'semanal':
            horas += 168
        elif visao == 'mensal':
            mes, ano = map(int, p.split('/'))
            dias_no_mes = calendar.monthrange(ano, mes)[1]
            horas += dias_no_mes * 24
    return horas

# --- CABEÇALHO ---
col1, col2 = st.columns([3, 1])
with col1:
    st.title("📊 Relatório de Disponibilidade Física")
with col2:
    # Substitua a URL abaixo pela sua logomarca
    st.image("https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcT2y4RDy3dJMu1cyGiZwdmtHCopiNFuD2etAOmssdlvjO-k7JbJ9I_5LA&s=10", width=150)

# --- PAINEL DE CONTROLO ---
with st.expander("🛠️ PAINEL DE CONTROLO E FILTROS", expanded=True):
    c1, c2, c3, c4 = st.columns(4)
    file_upload = c1.file_uploader("1. Ficheiro Excel", type=['xlsx', 'xls'])
    
    if file_upload:
        df_bruto = carregar_dados(file_upload)
        
        if df_bruto is not None and not df_bruto.empty:
            visao = c2.selectbox("2. Visão", ['diario', 'semanal', 'mensal'], format_func=lambda x: x.capitalize())
            
            # Ordenar Períodos decrescentemente
            periodos_unicos = sorted(df_bruto[visao].unique(), reverse=True)
            periodos_selecionados = c3.multiselect("3. Período(s) (Múltiplos permitidos)", periodos_unicos, default=[periodos_unicos[0]])
            
            modelos_unicos = ["Todos os Modelos"] + sorted(df_bruto['MODELO'].unique())
            modelo_selecionado = c4.selectbox("4. Modelo", modelos_unicos)
            
            c5, c6, c7, c8, c9 = st.columns([1, 1, 1, 1, 1])
            meta_input = c5.number_input("5. Meta DF (%)", min_value=0.0, max_value=100.0, value=90.0, step=0.5)
            meta_real = meta_input / 100.0
            
            ordem_df = c6.selectbox("6. Ordem Gráfico DF", [
                'DF (Menor p/ Maior)', 'DF (Maior p/ Menor)', 'Equipamento (A-Z)', 'Equipamento (Z-A)'
            ])
            
            qtd_dias = c7.number_input("7a. Hist. Dias", value=7, min_value=1)
            qtd_semanas = c8.number_input("7b. Hist. Semanas", value=4, min_value=1)
            qtd_meses = c9.number_input("7c. Hist. Meses", value=12, min_value=1)

# --- EXECUÇÃO DO DASHBOARD ---
if file_upload and df_bruto is not None and len(periodos_selecionados) > 0:
    
    # 1. Filtro Base (Período e Modelo)
    df_filtrado = df_bruto[df_bruto[visao].isin(periodos_selecionados)].copy()
    
    # Identificar equipamentos válidos do Modelo
    if modelo_selecionado != "Todos os Modelos":
        eqp_validos = df_bruto[df_bruto['MODELO'] == modelo_selecionado]['EQUIPAMENTO'].unique()
    else:
        eqp_validos = df_bruto['EQUIPAMENTO'].unique()
        
    df_filtrado = df_filtrado[df_filtrado['EQUIPAMENTO'].isin(eqp_validos)]
    horas_base_total = calcular_horas_base(visao, periodos_selecionados)
    
    # 2. Cálculo DF por Equipamento
    agrupado_eqp = df_filtrado.groupby('EQUIPAMENTO')['TOTAL HORAS DECIMAIS'].sum().reset_index()
    # Adicionar os que tiveram 0 paragens
    todos_eqp_df = pd.DataFrame({'EQUIPAMENTO': eqp_validos})
    agrupado_eqp = pd.merge(todos_eqp_df, agrupado_eqp, on='EQUIPAMENTO', how='left').fillna(0)
    
    agrupado_eqp['DF'] = (horas_base_total - agrupado_eqp['TOTAL HORAS DECIMAIS']) / horas_base_total
    agrupado_eqp['DF'] = agrupado_eqp['DF'].apply(lambda x: max(0, x))
    agrupado_eqp['DF_Perc'] = agrupado_eqp['DF'] * 100
    agrupado_eqp['Cor'] = agrupado_eqp['DF_Perc'].apply(lambda x: '#555555' if x >= meta_input else '#d32f2f')

    # Ordenação
    if ordem_df == 'DF (Menor p/ Maior)':
        agrupado_eqp = agrupado_eqp.sort_values(['DF_Perc', 'EQUIPAMENTO'], ascending=[True, True])
    elif ordem_df == 'DF (Maior p/ Menor)':
        agrupado_eqp = agrupado_eqp.sort_values(['DF_Perc', 'EQUIPAMENTO'], ascending=[False, True])
    elif ordem_df == 'Equipamento (A-Z)':
        agrupado_eqp = agrupado_eqp.sort_values('EQUIPAMENTO', ascending=True)
    else:
        agrupado_eqp = agrupado_eqp.sort_values('EQUIPAMENTO', ascending=False)

    # 3. ABAS
    aba1, aba2 = st.tabs(["📊 Dashboard Principal", "📈 Acumulados & Tendências"])

    # ==========================================
    # ABA 1: DASHBOARD PRINCIPAL
    # ==========================================
    with aba1:
        st.markdown(f"**Visão:** {visao.capitalize()} | **Período(s):** {', '.join(periodos_selecionados)}")
        
        col_g1, col_g2 = st.columns(2)
        
        # Gráfico 1: DF por Equipamento
        with col_g1:
            fig_eqp = go.Figure()
            fig_eqp.add_trace(go.Bar(
                x=agrupado_eqp['EQUIPAMENTO'], 
                y=agrupado_eqp['DF_Perc'],
                marker_color=agrupado_eqp['Cor'],
                text=agrupado_eqp['DF_Perc'].apply(lambda x: f"{x:.0f}%"),
                textposition='auto'
            ))
            fig_eqp.add_hline(y=meta_input, line_dash="dash", line_color="#d32f2f", annotation_text=f"Meta {meta_input}%", annotation_position="top left")
            fig_eqp.update_layout(title="DF POR EQUIPAMENTO (%)", template="plotly_white", margin=dict(t=40, b=0, l=0, r=0))
            # Escala dinâmica do eixo Y
            min_y = max(0, agrupado_eqp['DF_Perc'].min() - 5)
            if min_y > meta_input: min_y = meta_input - 5
            fig_eqp.update_yaxes(range=[min_y, 105])
            st.plotly_chart(fig_eqp, use_container_width=True)

        # Gráfico 2: Resp Nivel 1 (Donut)
        with col_g2:
            agrupado_r1 = df_filtrado.groupby('RESPONSABILIDADE NÍVEL 1')['TOTAL HORAS DECIMAIS'].sum().reset_index()
            fig_r1 = px.pie(agrupado_r1, names='RESPONSABILIDADE NÍVEL 1', values='TOTAL HORAS DECIMAIS', hole=0.5, 
                            title="HORAS PARADAS POR RESP. NÍVEL 1",
                            color_discrete_sequence=['#111', '#444', '#777', '#aaa'])
            fig_r1.update_traces(textinfo='percent+value')
            fig_r1.update_layout(margin=dict(t=40, b=0, l=0, r=0))
            st.plotly_chart(fig_r1, use_container_width=True)

        col_g3, col_g4 = st.columns(2)
        
        # Gráfico 3: Resp Nivel 2
        with col_g3:
            agrupado_r2 = df_filtrado.groupby('RESPONSABILIDADE NÍVEL 2')['TOTAL HORAS DECIMAIS'].sum().nlargest(10).reset_index()
            agrupado_r2 = agrupado_r2.sort_values('TOTAL HORAS DECIMAIS', ascending=True)
            fig_r2 = px.bar(agrupado_r2, x='TOTAL HORAS DECIMAIS', y='RESPONSABILIDADE NÍVEL 2', orientation='h', 
                            title="ACUMULADO: RESP. NÍVEL 2 (TOP 10)", color_discrete_sequence=['#444'])
            fig_r2.update_layout(template="plotly_white", margin=dict(t=40, b=0, l=0, r=0), yaxis_title="")
            st.plotly_chart(fig_r2, use_container_width=True)
            
        # Gráfico 4: Detalhamento
        with col_g4:
            agrupado_det = df_filtrado.groupby('DETALHAMENTO')['TOTAL HORAS DECIMAIS'].sum().nlargest(10).reset_index()
            agrupado_det = agrupado_det.sort_values('TOTAL HORAS DECIMAIS', ascending=True)
            # Limitar tamanho do label
            agrupado_det['DETALHAMENTO'] = agrupado_det['DETALHAMENTO'].apply(lambda x: x[:30]+'...' if len(x)>30 else x)
            fig_det = px.bar(agrupado_det, x='TOTAL HORAS DECIMAIS', y='DETALHAMENTO', orientation='h', 
                             title="ACUMULADO: DETALHAMENTO (TOP 10)", color_discrete_sequence=['#444'])
            fig_det.update_layout(template="plotly_white", margin=dict(t=40, b=0, l=0, r=0), yaxis_title="")
            st.plotly_chart(fig_det, use_container_width=True)

        # TABELA: Abaixo da Meta
        st.markdown("### 🔻 EQUIPAMENTOS ABAIXO DA META SELECIONADA")
        abaixo_meta = agrupado_eqp[agrupado_eqp['DF_Perc'] < meta_input].copy()
        
        if abaixo_meta.empty:
            st.success("🎉 Excelente! Nenhum equipamento selecionado ficou abaixo da meta.")
        else:
            tabela_dados = []
            for _, row in abaixo_meta.iterrows():
                eqp = row['EQUIPAMENTO']
                df_calc = row['DF_Perc']
                dif = meta_input - df_calc
                tot_horas = row['TOTAL HORAS DECIMAIS']
                
                # Pegar causas
                causas_eqp = df_filtrado[df_filtrado['EQUIPAMENTO'] == eqp].groupby('CAUSA')['TOTAL HORAS DECIMAIS'].sum().nlargest(5)
                
                causas_str = f"Total Acumulado: {tot_horas:.2f}h\n"
                for causa, hrs in causas_eqp.items():
                    perc = (hrs / tot_horas) * 100 if tot_horas > 0 else 0
                    causas_str += f"• {causa} [{hrs:.2f}h ➔ {perc:.1f}%]\n"
                
                tabela_dados.append({
                    "Equipamento": eqp,
                    "Meta DF": f"{meta_input:.2f}%",
                    "DF Calculado": f"{df_calc:.2f}%",
                    "Diferença": f"-{dif:.2f}%",
                    "Principais Fatores Contribuintes": causas_str
                })
            
            st.dataframe(pd.DataFrame(tabela_dados), use_container_width=True)

    # ==========================================
    # ABA 2: ACUMULADOS E TENDÊNCIAS
    # ==========================================
    with aba2:
        max_data = df_bruto[df_bruto[visao].isin(periodos_selecionados)]['DATA INÍCIO'].max()
        if pd.isna(max_data):
            max_data = df_bruto['DATA INÍCIO'].max()
            
        ref_mes_str = max_data.strftime('%m/%Y')
        st.markdown(f"**Mês de Referência para DF Global:** {ref_mes_str}")
        
        # 1. Cartões por Modelo
        modelos_disponiveis = [modelo_selecionado] if modelo_selecionado != "Todos os Modelos" else df_bruto['MODELO'].unique()
        modelos_disponiveis = [m for m in modelos_disponiveis if m != "N/A"]
        
        cols = st.columns(len(modelos_disponiveis) if len(modelos_disponiveis) > 0 else 1)
        for i, mod in enumerate(modelos_disponiveis):
            eqps_mod = df_bruto[df_bruto['MODELO'] == mod]['EQUIPAMENTO'].unique()
            df_mes_mod = df_bruto[(df_bruto['mensal'] == ref_mes_str) & (df_bruto['EQUIPAMENTO'].isin(eqps_mod))]
            
            eqps_ativos = df_mes_mod['EQUIPAMENTO'].unique()
            if len(eqps_ativos) > 0:
                dias_no_mes = calendar.monthrange(max_data.year, max_data.month)[1]
                h_base_mes = dias_no_mes * 24 * len(eqps_ativos)
                h_paradas = df_mes_mod['TOTAL HORAS DECIMAIS'].sum()
                df_global = max(0, (h_base_mes - h_paradas) / h_base_mes) * 100
                
                cor_classe = "good" if df_global >= meta_input else "bad"
                
                with cols[i % len(cols)]:
                    st.markdown(f"""
                    <div class="card">
                        <div class="card-title">{mod}</div>
                        <div class="metric-subtitle">DF Global Mensal</div>
                        <div class="card-value {cor_classe}">{df_global:.2f}%</div>
                    </div>
                    """, unsafe_allow_html=True)

        # 2. Função de Geração de Gráfico de Linhas (Evolução)
        def desenhar_grafico_evolucao(tipo_visao, limite, titulo):
            periodos_disp = sorted(df_bruto[tipo_visao].dropna().unique(), reverse=True)
            
            # Achar index de referência (baseado no periodo máximo selecionado)
            target_val = df_bruto[df_bruto[visao].isin(periodos_selecionados)][tipo_visao].max()
            if not target_val or target_val not in periodos_disp:
                target_val = periodos_disp[0]
                
            idx = periodos_disp.index(target_val)
            periodos_grafico = periodos_disp[idx : idx + limite][::-1] # Inverte para Ordem Cronológica no Eixo X
            
            if not periodos_grafico:
                st.info(f"Sem dados suficientes para {titulo}")
                return
                
            dados_linha = []
            for p in periodos_grafico:
                for mod in modelos_disponiveis:
                    eqps_mod = df_bruto[df_bruto['MODELO'] == mod]['EQUIPAMENTO'].unique()
                    
                    df_p = df_bruto[(df_bruto[tipo_visao] == p) & (df_bruto['EQUIPAMENTO'].isin(eqps_mod))]
                    
                    # Para saber os equipamentos ativos daquele modelo naquele periodo específico (Para o H_Base exato)
                    eqps_ativos = df_p['EQUIPAMENTO'].unique()
                    if len(eqps_ativos) == 0:
                        continue
                        
                    h_base = calcular_horas_base(tipo_visao, [p]) * len(eqps_ativos)
                    h_paradas = df_p['TOTAL HORAS DECIMAIS'].sum()
                    
                    df_calc = max(0, (h_base - h_paradas) / h_base) * 100
                    dados_linha.append({'Período': p, 'Modelo': mod, 'DF': df_calc})
                    
            if not dados_linha:
                return

            df_plot = pd.DataFrame(dados_linha)
            
            fig = px.line(df_plot, x='Período', y='DF', color='Modelo', markers=True, title=titulo,
                          color_discrete_sequence=['#3b82f6', '#f59e0b', '#10b981', '#8b5cf6', '#06b6d4'])
            
            fig.add_hline(y=meta_input, line_dash="dash", line_color="#d32f2f", annotation_text=f"Meta {meta_input}%")
            fig.update_layout(template="plotly_white", margin=dict(t=40, b=0, l=0, r=0), yaxis_title="DF (%)", xaxis_title="")
            # Escala dinâmica
            fig.update_yaxes(range=[max(0, df_plot['DF'].min() - 5), 105])
            
            st.plotly_chart(fig, use_container_width=True)

        # Desenha os 3 gráficos
        c_diario, c_semanal = st.columns(2)
        with c_diario:
            desenhar_grafico_evolucao('diario', qtd_dias, f"EVOLUÇÃO DIÁRIA (ÚLT. {qtd_dias} DIAS)")
        with c_semanal:
            desenhar_grafico_evolucao('semanal', qtd_semanas, f"EVOLUÇÃO SEMANAL (ÚLT. {qtd_semanas} SEMANAS)")
            
        desenhar_grafico_evolucao('mensal', qtd_meses, f"EVOLUÇÃO MENSAL (ÚLT. {qtd_meses} MESES)")

    # Informação sobre a exportação para PDF (Dica nativa do navegador/Streamlit)
    st.sidebar.markdown("""
    ### 📄 Como exportar para PDF?
    No Streamlit, para exportar este Dashboard perfeito:
    1. Clique nos três pontinhos `⋮` no canto superior direito do ecrã.
    2. Escolha **"Print"** (Imprimir).
    3. Selecione a impressora **"Save as PDF"** (Guardar como PDF).
    4. Escolha o Layout **"Landscape"** (Paisagem) e ative **"Background graphics"**.
    """)
