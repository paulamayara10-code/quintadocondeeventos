# Quinta do Conde - Sistema Comercial + Gestão de Eventos (V2)

Versão mais estratégica do sistema, voltada para uso comercial e operacional.

## O que esta versão tem
- CRM básico de clientes
- cadastro de espaços
- cadastro de tipos de evento
- pipeline comercial
- proposta com formação de preço
- agenda comercial por espaço
- financeiro por evento
- serviços adicionais da proposta
- checklist operacional
- relatórios gerenciais

## Como rodar
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Banco de dados
O arquivo `eventos_fazenda_v2.db` será criado automaticamente na primeira execução.

## Observações
- O sistema já vem com espaços e tipos de evento sugeridos.
- Há bloqueio de conflito por data e espaço.
- O valor total da proposta é atualizado pela formação comercial.
