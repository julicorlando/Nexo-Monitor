# Integrações de leitura

## MikroTik RouterOS 7
Tipo mikrotik, porta HTTPS do www-ssl e credential_key=ROUTER. No coletor, NEXO_ROUTER_USER, NEXO_ROUTER_PASSWORD e opcional NEXO_ROUTER_CA (caminho do certificado CA). Consulta GET /rest/system/resource e /rest/interface. Exibe CPU/memória/uptime e contadores cumulativos das primeiras 50 interfaces; não calcula velocidade em Mbps nem modifica configuração. Configure usuário de leitura, TLS e acesso só do coletor conforme https://manual.mikrotik.com/docs/developer-guides/rest-api/. O suporte deve ser testado no RouterOS instalado; não aplicamos alterações ao seu roteador.

## UniFi Network
Tipo unifi, host/porta do controlador HTTPS, credential_key=UNIFI, NEXO_UNIFI_API_KEY e opcional NEXO_UNIFI_CA. Configure integration_path com endpoint de listagem de dispositivos da API oficial da versão instalada. Referência https://developer.ui.com/. O parser espera objeto com data contendo dispositivos e campos name/id/state/ipAddress. Lista até 50 da página recebida e considera ONLINE saudável. Consulta até dez páginas/500 dispositivos; avalia todos os recebidos e exibe resumo dos primeiros 50. Uma coleta incompleta não é considerada saudável. Não consulta clientes ou estatísticas Wi-Fi e não suporta API legada baseada em login/cookie. Antes de instalar confirme o controlador e a versão. Respostas incompatíveis geram falha, sem inventar dados.

## Hikvision ISAPI
Tipo hikvision, credential_key=NVR. Configure NEXO_NVR_USER, NEXO_NVR_PASSWORD e NEXO_NVR_CA opcional. Usa HTTPS com Digest, GET /ISAPI/ContentMgmt/Storage por padrão, caminho configurável. Analisa elementos hdd/HDD com status, capacity/freeSpace/id. Somente ok/normal são saudáveis; ausência de campos suportados gera falha. Compatibilidade depende do modelo/firmware. Leitura do disco não comprova gravação: recording_verified=false. Referência https://open.hikvision.com/.

## Intelbras e comprovação de gravação
Sem modelos/firmwares e documentação de API correspondente, nenhum endpoint proprietário de Intelbras é presumido. Use TCP/HTTPS/SNMP quando suportado. Leitura de discos e verificação de gravação recente Intelbras/Hikvision continuam dependentes da documentação e da homologação dos modelos reais. Não existe integração universal que comprove gravação apenas com ping.

## Switches / impressoras / REP
snmpwalk consulta uma subárvore indicada em snmp_oid, com comunidade local NEXO_SNMP_CHAVE. Exibe até 50 linhas. OIDs de interfaces, PoE e toner dependem da MIB/modelo; não traduz automaticamente estados nem calcula tráfego por segundo. Use comunidade somente leitura em rede confiável/VPN. Suporta v2c e v3 com authPriv usando arquivo local privado; veja a seção SNMPv3 abaixo.

## Caixas / estacionamento / servidores
Use tcp/http para serviço remoto e service para processo/serviço local: service_name é nome do serviço Windows ou nome exato do processo Linux. O coletor precisa estar na máquina alvo. Isso verifica processo ativo, não resultado de transações ou permissões operacionais do sistema de terceiros. system mede CPU/memória/disco local usando psutil.

## SNMPv3 authPriv
Configure NEXO_SNMP_CHAVE_CONFIG com o diretório local que contém snmp.conf. O coletor passa SNMPCONFPATH apenas ao subprocesso; usa -v3 -l authPriv. Em Linux, o arquivo deve ter permissão 0600. Não há senha de autenticação/privacidade nos argumentos do processo. Configure o arquivo segundo o dispositivo e a versão net-snmp:

```text
defVersion 3
defSecurityName USUARIO_DO_EQUIPAMENTO
defSecurityLevel authPriv
defAuthType SHA
defAuthPassphrase SENHA_DE_AUTENTICACAO
defPrivType AES
defPrivPassphrase SENHA_DE_PRIVACIDADE
```

Proteja o arquivo fora do repositório. No Docker, monte o diretório como volume somente leitura e configure a variável para o caminho montado. Sem essa variável, usa v2c com NEXO_SNMP_CHAVE. Referências: https://www.net-snmp.org/docs/man/snmp.conf.html e https://www.net-snmp.org/docs/man/snmp_config.html. Configure as mesmas opções suportadas pelo switch/roteador; o coletor não muda a configuração do dispositivo. Validado com subprocesso simulado, não em hardware real.
