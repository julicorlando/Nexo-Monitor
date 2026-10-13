# Nexo Monitor

Central web em português para monitoramento e inventário de infraestrutura, com Django/PostgreSQL e coletores Python distribuídos. Instalação preparada para PowerEdge R230 + Coolify; nenhum acesso ou deploy foi realizado na rede real.

## Implementado
- Painel responsivo, inventário com formulários, unidades, importação CSV e permissões por unidade.
- TCP, HTTPS, ping, recursos locais CPU/RAM/disco, serviço Windows/processo Linux, SNMP v2c/v3 consulta/subárvore.
- Adaptadores de leitura MikroTik REST, UniFi via API key/caminho configurável e status de discos Hikvision ISAPI.
- Gráficos de latência, histórico por horário observado e disponibilidade por amostras recebidas.
- Incidentes, confirmação por falhas consecutivas, dependências e manutenção programada.
- Alertas de falha/recuperação e perda/retorno do coletor, via SMTP e WhatsApp com QR code e único destinatário autorizado.
- Fila SQLite persistente no coletor, cache de configuração, reenvio idempotente e preservação do estado mais recente.
- MFA TOTP opcional com proteção de replay, segredo criptografado, limitação de tentativas de login e auditoria.
- Docker Compose, worker, migrações automáticas, healthcheck web/banco, retenção de amostras e instruções de backup.
- Script de monitor externo para a própria central.

## Instalação
Leia [Operação](docs/OPERACAO.md), [Integrações](docs/INTEGRACOES.md) e [WhatsApp](docs/WHATSAPP.md). Para WhatsApp/QR selecione compose.whatsapp.yaml. Use compose.yaml no Coolify; copie os nomes das variáveis de .env.example. Gere SECRET_KEY e POSTGRES_PASSWORD distintos, configure ALLOWED_HOSTS (domínio sem protocolo + localhost,127.0.0.1), CSRF_TRUSTED_ORIGINS (domínio HTTPS) e SMTP. Após deploy: `python manage.py createsuperuser` no terminal web. Cadastre unidades/coletores e gere um token com `python manage.py issue_collector_token ID`. Cada unidade precisa de coletor com acesso à rede local.

Nunca versione senhas, tokens ou dumps. Preserve SECRET_KEY: a troca exige reconfigurar MFA. O monitor externo deve ficar em outra rede/máquina. Banco não tem porta pública. Configuração de rede/API dos equipamentos não é alterada pelo sistema.

## Desenvolvimento
```bash
pip install -r requirements.txt -r collector/requirements.txt
export SECRET_KEY=chave-apenas-para-desenvolvimento
export DEBUG=true
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
python manage.py test
```

## Limites e validação pendente
Não presume IPs, usuários, versões ou respostas dos equipamentos reais. Os conectores foram testados com respostas simuladas. Intelbras proprietário, gravação recente, MIBs específicas PoE/toner/REP e clientes/estatísticas Wi-Fi UniFi dependem de modelos/documentação e homologação. SNMP aceita v2c/v3 e não calcula taxas de tráfego. UniFi consulta até dez páginas de API compatível, sem API legada. O gráfico de disponibilidade é baseado em amostras; períodos sem coleta não são uptime confirmado. Recursos locais medem o host do coletor ou container onde estiver instalado.

O inventário usa HTML/CSS com Django; React/Redis não são necessários nesta etapa. O SMTP realiza entrega com possibilidade de repetição após falha entre envio e confirmação. Uma única réplica do worker. Unidades, coletores e destinatários de e-mail podem ser cadastrados nas telas do painel por superusuário; usuários continuam na administração Django. Auditoria cobre login, MFA, alterações no inventário/importação e administração de modelos monitorados; não registra mudanças feitas diretamente no banco. Retenção de amostras: 30 dias; fila offline: seis dias/10.000 lotes. Backups, SMTP, APIs e instalação Coolify precisam ser testados no ambiente real antes de declarar a operação homologada.

## Primeira configuração e pendências
Após o primeiro login de administrador sem unidades, o painel abre `/setup/`. O guia também está no menu. Etapas mostram evidência de cadastro/coleta/envio; não certificam homologação ou leitura de mensagens. Veja a lista completa em [Pendências](docs/PENDENCIAS.md).
