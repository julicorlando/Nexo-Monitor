# Nexo Monitor

Central web em português para inventário e monitoramento de infraestrutura em múltiplas unidades. Primeira versão funcional em Django, PostgreSQL e HTML/CSS responsivo. O coletor Python utiliza apenas a biblioteca padrão.

## Disponível nesta versão
- Login, sessões e administração de usuários pelo Django.
- Unidades, coletores e equipamentos; categorias para o inventário informado.
- Verificação de portas TCP com coletor local ou em outras unidades, conexões de saída HTTPS.
- Painel com status e latência; dados com mais de 180 segundos ficam sem confirmação recente.
- Histórico de verificações e incidentes com resolução automática.
- Token exclusivo por coletor, armazenado somente como SHA-256; isolamento dos resultados por coletor.
- Docker Compose com PostgreSQL persistente, healthchecks, migrations no deploy e processo web sem root.

## Implantar no Coolify / PowerEdge R230
1. Crie um recurso Docker Compose apontando para este repositório e `compose.yaml`.
2. Gere valores distintos e fortes para SECRET_KEY e POSTGRES_PASSWORD. Exemplo local: `python -c 'import secrets; print(secrets.token_urlsafe(48))'`.
3. Configure ALLOWED_HOSTS com o domínio **sem protocolo**, incluindo `localhost,127.0.0.1` para o healthcheck; configure CSRF_TRUSTED_ORIGINS com `https://seu-dominio`.
4. Associe o domínio ao serviço web na porta 8000, habilite HTTPS e faça deploy. PostgreSQL não precisa de porta pública.
5. No terminal do serviço web, execute `python manage.py createsuperuser`. Acesse `/admin/`.
6. Cadastre a unidade, o coletor e os equipamentos com IP/hostname e uma porta realmente aberta (ex.: interface HTTPS 443 ou RTSP 554). Equipamentos sem serviço TCP acessível não podem ser avaliados corretamente nesta versão.
7. Gere o token: `python manage.py issue_collector_token ID`. Copie-o para o coletor; repetir o comando revoga o token anterior.
8. Em uma máquina da rede monitorada com Python 3.12, configure NEXO_URL e NEXO_TOKEN como variáveis de ambiente e execute `python collector/agent.py`. Configure o processo como serviço com reinício automático. Em outras unidades, repita com outro coletor/token.
9. Agende `python manage.py prune_results` diariamente para retenção de 30 dias. Configure backups externos do PostgreSQL e teste restauração.

O inventário não vem preenchido com IPs inventados. Coletores aceitam até 500 resultados por lote. Cada ciclo ocorre a cada 60 segundos, após a conclusão do anterior. Falhas de comunicação com a central ficam nos logs; a próxima coleta recupera o estado atual, sem fila persistente de resultados.

## Desenvolvimento e testes
```bash
pip install -r requirements.txt
export SECRET_KEY=chave-local-de-desenvolvimento
export DEBUG=true
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
python manage.py test
```

## Próximas integrações
SNMP, MikroTik, UniFi, agentes de CPU/RAM/disco, estado de gravação Intelbras/Hikvision, notificações por e-mail, gráficos, permissões por unidade e MFA. React e Redis poderão entrar quando houver necessidade de interface e processamento mais complexos. Não estão implementados nesta versão.

TCP disponível não equivale a aplicação saudável. A central no R230 ficará indisponível se ele ou o link da matriz cair; para detectar essa condição é necessário um monitor externo independente. Não exponha interfaces administrativas dos equipamentos na internet. Use HTTPS na central e acesso administrativo restrito.
