# Chromis WEB

Software de dosimetria com filmes radiocrômicos EBT3/EBT4 para radioterapia.
Calibração, mapas de dose 2D, isodoses, análise gamma (AAPM TG-218),
controle de qualidade (dose pontual, perfis, simetria de bordas, isocentro
mecânico) e geração de relatórios em PT/EN.

Desenvolvido por **MACIEL, J. O.**

---

## Funcionalidades

**Configuração**
- Setup do estudo (clínico/acadêmico, máquina, energia, filme, scanner)
- Importação do planejamento do TPS (Monaco): RT Dose, isodoses, pontos
- Upload de imagens dos filmes com pré-visualização

**Controle de Qualidade**
- Dose pontual e perfis de dose (comparação por coordenadas)
- Simetria de bordas (flatness, simetria, penumbra)
- Isocentro mecânico (star shot)

**Análise Dosimétrica**
- Curva de calibração (Power Law, Polinomial, Racional, Spline)
- Mapa de dose 2D
- Mapa de isodose (filme vs TPS)
- Análise gamma (critérios TG-218)

**Saída**
- Relatório PDF total ou parcial, em português ou inglês

---

## Tecnologia

- Python + Streamlit
- Tema escuro, interface bilíngue (PT-BR / EN-US)
- Sistema de cadastro com aprovação por administrador

---

## Como rodar

Veja o **[GUIA_CONFIGURACAO.md](GUIA_CONFIGURACAO.md)** para instruções
completas de instalação, configuração de email e deploy.

Resumo:
```bash
pip install -r requirements.txt
streamlit run app.py
```

---

## Estrutura

| Arquivo/pasta | Função |
|---|---|
| `app.py` | Aplicativo principal (navegação, login, dashboard) |
| `admin_panel.py` | Aprovação de cadastros |
| `i18n.py` | Traduções PT/EN |
| `theme.py` | Tema escuro e componentes visuais |
| `auth/` | Cadastro, login, notificações por email |
| `views/` | Telas de cada módulo |
| `assets/` | Logos |
| `calibration.py`, `gamma_engine.py`, ... | Motores de cálculo |

---

## Validação científica

Baseado nas recomendações **AAPM TG-218** para análise gamma e nas
referências de dosimetria com filmes radiocrômicos.

---

## Licença

Defina a licença do projeto (ex: MIT) conforme sua preferência.
