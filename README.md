# Quinta do Conde - Sistema Comercial + Gestão de Eventos (V4)

Versão com proposta em PDF e formação manual.

## Como os dados ficam armazenados
- o sistema usa banco local SQLite
- o arquivo do banco se chama `eventos_fazenda_v4.db`
- ele é criado automaticamente na primeira execução
- todos os cadastros ficam gravados nesse arquivo

## Risco de perda
Existe risco se:
- apagar o arquivo `.db`
- trocar de máquina sem copiar o banco
- rodar em ambiente temporário sem persistência
- corromper a pasta do projeto

## Como evitar perda
- manter a pasta do sistema em local fixo
- fazer backup periódico do arquivo `.db`
- se usar GitHub/Streamlit Cloud, não usar SQLite como base principal de produção
- para produção real, o ideal é migrar para banco persistente como PostgreSQL/Supabase

## Como rodar
```bash
pip install -r requirements.txt
streamlit run app.py
```
