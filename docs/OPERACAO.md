# Instalação e operação

## Coolify
Use a branch main e compose.yaml (ou compose.whatsapp.yaml para incluir WhatsApp/QR). Configure as variáveis de .env.example, domínio HTTPS no serviço web/8000 e disco persistente do PostgreSQL. Não associe domínio ao worker ou banco. O worker precisa de uma réplica apenas. Crie o superusuário pelo terminal do serviço web. Cadastre unidades/coletores e e-mails pelas telas Unidades e Alertas. Ao criar coletor ou rotacionar seu token, copie o valor exibido uma única vez. Migrations rodam antes do Gunicorn; worker espera healthcheck web.

## Coletores
Para métricas do host, execute Python nativamente. Linux precisa de ping/net-snmp, Windows precisa de Python e psutil; SNMP exige instalação de net-snmp compatível. Configure NEXO_URL, NEXO_TOKEN e opcionalmente NEXO_SPOOL_PATH. Execute `python collector/agent.py` como serviço com reinício. Um único processo por arquivo SQLite. O diretório da fila precisa ser gravável e persistente. No Docker use collector/compose.yaml. Configure as variáveis de integração no serviço do coletor: não as envie ao painel.

A fila guarda até seis dias e 10.000 lotes, descartando os antigos se atingir o limite. Configuração é mantida em cache. Reenvio usa UUID por lote e horário UTC; lotes inválidos (equipamento removido/desativado) são descartados com registro em log. Sincronize os relógios com NTP. O estado atual não é sobrescrito por uma amostra mais antiga. Receber amostras históricas não comprova funcionamento atual. Não haverá fila histórica antes de iniciar o coletor.

## Dependências e manutenção
Configure equipamento pai no inventário (ex.: roteador principal). Falhas do dependente ficam registradas; seu alerta é suprimido enquanto o pai está sem confirmação ou indisponível. Incidentes suprimidos são fechados sem alerta de recuperação. Use manutenção até uma data/hora para silenciar alertas do equipamento. A regra é avaliada a cada lote e pelo worker para equipamentos com dados recentes. Não altera a coleta.

## MFA
Em Segurança, adicione manualmente a chave TOTP a um autenticador e confirme com senha/código. A chave armazenada é criptografada usando SECRET_KEY; preserve essa chave nos backups. Login público e login do Django Admin exigem código quando ativo. Sessões anteriores são encerradas ao acessar telas protegidas após a ativação. Recuperação: `python manage.py reset_mfa USUARIO` no terminal autorizado. Reative o MFA após recuperar. Não há códigos de recuperação nem QR nesta versão.

## Backup PostgreSQL
No host, adapte os nomes dos containers obtidos no Coolify. Execute um dump com `docker exec CONTAINER_DB pg_dump -U nexo -Fc nexo > nexo-backup.dump`. Guarde também SECRET_KEY e as variáveis de integração em um cofre separado e copie os backups para outro servidor. Não versione dumps ou segredos. Teste a restauração em ambiente isolado usando `pg_restore -U nexo -d nexo --clean --if-exists` com o arquivo transferido ao container; pare web/worker antes de restaurar uma base em uso. Defina retenção e agendamento no host/Coolify. Backup e restauração não foram executados no R230.

## Monitor independente
Rode collector/external_probe.py em outra máquina/rede, apontando NEXO_EXTERNAL_URL para https://dominio/health/. Configure SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD, SMTP_FROM e SMTP_TO. O script avisa mudança de estado; exige STARTTLS. Inicialização também envia estado atual. Não foi instalado em servidor externo nesta entrega.

## Homologação na rede real
- Validar DNS/HTTPS/login/MFA no celular e computador.
- Comparar um equipamento online/offline com estado observado.
- Interromper internet do coletor, conferir fila, retornar e verificar histórico sem duplicação.
- Derrubar roteador pai e conferir agrupamento.
- Testar manutenção, destinatários e e-mail de recuperação.
- Confirmar leitura de métricas e serviços em cada SO.
- Validar APIs e versões dos fabricantes e restaurar um backup isolado.

## Saúde da coleta e perfis
A tela Saúde da coleta mostra último contato do worker, versão/erros/fila dos coletores. Atualize e reinicie os coletores com o código da mesma versão para enviarem diagnóstico. Mais de 1.000 lotes ou erro informado gera um alerta; a verificação individual atrasada é detectada quando o coletor ainda está conectado. Os dados locais somente chegam quando a comunicação retorna.

Configure o monitor externo para `https://dominio/health/monitoring/` para detectar worker sem contato por cinco minutos ou erro registrado. `/health/` continua sendo a verificação de web/banco usada no deploy: não depende do worker para evitar dependência circular. A própria central não consegue enviar pelo worker parado; o script externo precisa estar em outra máquina e com SMTP próprio.

Papéis são criados pelo deploy ou por `python manage.py configure_roles`: Visualizador, Configurador (cadastro/alteração de equipamentos) e Operador de incidentes (reconhecimento, responsável e observações). Associe grupos pelo cadastro de usuários no Admin e associe a unidade em Site.members. Grupos não dão acesso a unidades automaticamente; superusuários têm administração global. Não atribua `is_staff` a operadores comuns sem necessidade de Admin. Os grupos Nexo são gerenciados pelo comando e suas permissões são reaplicadas no deploy.

Arquivar retira o equipamento da coleta e do painel operacional, fecha seus incidentes e preserva amostras/auditoria. Restaurar exige novas amostras e reativa a coleta. Arquivamento não impede a política de retenção de apagar amostras antigas após 30 dias. Edite as quantidades de falhas e sucessos consecutivos para controlar confirmação de queda e recuperação. A prévia de alerta é explicativa e não executa testes reais nem envia mensagens.

Auditoria de configuração registra antes/depois de campos de equipamentos, unidades, coletores e destinatários pelas telas e campos escalares pelo Admin. Segredos de autenticação do coletor/gateway não são registrados. Eventos antigos permanecem sem detalhe de campos. Alterações diretas no banco ou scripts externos não são capturadas.
