# Quinta do Conde - Sistema Comercial + Gestão de Eventos (V5)

## Novidades desta versão
- opção de exportar backup completo em Excel
- opção de importar o mesmo backup para restaurar a base
- inclusão via sistema permanece normal
- proposta em PDF mantida
- layout refinado com paleta mais inspirada no estilo rústico/elegante da Quinta do Conde

## Como funciona o backup
- o sistema continua sendo o ponto principal de cadastro
- o Excel funciona como backup e intercâmbio padronizado
- a importação substitui a base atual do sistema

## Como rodar
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Arquivos importantes
- `eventos_fazenda_v5.db` = base local SQLite
- backup Excel = arquivo exportado pela tela "Backup Excel"
