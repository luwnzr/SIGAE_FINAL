# SIGAE – Sistema Inteligente de Gestão de Ativos e Empréstimos

Python + Django 5 + Bootstrap 5. Banco de dados: **SQLite** (arquivo `db.sqlite3`, dentro desta pasta).

---

## 1. Entrar no sistema (todo dia)

1. Abra o **VS Code** → **Arquivo → Abrir Pasta** → escolha `C:\Users\luane\Downloads\SIGAE\sigae`
2. Abra o terminal do VS Code: menu **Terminal → Novo Terminal** 
3. Rode:

   ```powershell
   .\iniciar.ps1
   ```

4. Abra no navegador: **http://127.0.0.1:8000** (depois `Ctrl + F5` se o visual parecer antigo)
5. Para desligar: clique no terminal e aperte `Ctrl + C`

> Se o PowerShell reclamar que "a execução de scripts foi desabilitada", rode uma vez:
> `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` (responda `S`) e tente de novo.

O `iniciar.ps1` já ativa o ambiente (`.venv`), cria/atualiza as tabelas, garante os dados básicos
(turmas, instrutores, alunos e notebooks 1–45) e liga o servidor. Pode rodar quantas vezes quiser.

### Usuários (senha de todos: `sigae@2026`)

| Perfil | Usuário | O que faz |
| Administrador | `admin.sigae` | Registra entrega e devolução dos notebooks |
| Instrutor | `instrutor.a` (Matutino e Vespertino), `instrutor.b` (Noturno) | Reserva notebooks para a turma |
| Aluno | `aluno01` … `aluno15` | Solicita o notebook reservado para a sua turma |

Alunos: 01–05 Matutino (Turma A) · 06–10 Vespertino (Turma B) · 11–15 Noturno (Turma C).

---

## 2. Ver o banco de dados no VS Code

**Só na primeira vez:**

1. Clique no ícone de **Extensões** (quadradinhos na barra da esquerda) ou `Ctrl + Shift + X`
2. Pesquise **SQLite Viewer** e clique em **Instalar**

**Sempre que quiser olhar o banco:**

1. No **Explorador** (lado esquerdo), clique no arquivo **`db.sqlite3`**
   (se ele não aparecer, rode `.\iniciar.ps1` uma vez para criá-lo)
2. As tabelas aparecem numa lista. Clique numa tabela para ver as linhas, como uma planilha
3. Depois de usar o sistema, **feche e abra o `db.sqlite3` de novo** para ver os dados atualizados

### Tabelas principais

| Tabela | O que guarda |
|---|---|
| `core_equipamento` | Os notebooks (`numero` 1–45 e `status`) |
| `core_reserva` | Cada reserva/empréstimo: quem reservou, aluno, notebook, turno, datas de entrega e devolução |
| `core_turma` | Turmas, com turno e instrutor responsável |
| `core_user` | Pessoas que entram no sistema (administrador, instrutores e alunos) |
| `auth_group` | Os perfis: Aluno, Instrutor, Administrador |

> As demais (`django_*`, `auth_*`) são internas do Django, pode ignorar.

### Códigos que aparecem no banco

| Campo | Códigos |
|---|---|
| `status` do notebook | `DIS` Disponível · `RES` Reservado · `EMP` Emprestado · `MAN` Manutenção |
| `status` da reserva | `PEN` Pendente · `APR` Reservada · `ATI` Entregue (ativo) · `CON` Concluída · `CAN` Cancelada |
| `turno` | `MAT` Matutino · `VES` Vespertino · `NOT` Noturno |

Dica: **só olhe** o banco por lá. Para alterar dados, use o sistema, para não deixar notebook e reserva
inconsistentes entre si.

---

## 3. Fluxo do sistema

1. **Instrutor** → Equipamentos → reserva N notebooks para a sua turma (data + turno)
2. **Aluno** → Início → **Solicitar meu notebook** (o sistema mostra o número, ex.: Nº 45)
3. **Administrador** → Empréstimos → **Solicitações** → confere o número que o aluno mostrou → **Registrar entrega**
4. O notebook passa a aparecer em **Empréstimos → Ativos**, com o nome do aluno e a turma
5. Na devolução: Empréstimos → **Ativos** → **Confirmar devolução** (o notebook volta a ficar disponível)

---

## 4. Comandos úteis (terminal na pasta `sigae`, com `(.venv)` ativo)

| Para quê | Comando |
|---|---|
| Recriar reservas de exemplo de hoje | `python manage.py seed_demo --reset` |
| Criar outro administrador | `python manage.py createsuperuser` |
| Zerar tudo e começar do zero | Pare o servidor, apague `db.sqlite3` e rode `.\iniciar.ps1` |

Horário dos turnos (Matutino até 12h, Vespertino até 18h, Noturno depois): função `_turno_atual` em `core/views.py`.

---

## 5. Voltar a usar MySQL (opcional)

O padrão agora é SQLite. Para usar MySQL (Workbench), crie o banco `sigae` e, no terminal:

```powershell
$env:DB_ENGINE="mysql"
$env:DB_NAME="sigae"
$env:DB_USER="root"
$env:DB_PASSWORD="SUA_SENHA"
$env:DB_HOST="127.0.0.1"
$env:DB_PORT="3306"
python manage.py migrate
python manage.py seed
python manage.py runserver
```

Essas variáveis valem só para o terminal aberto.

---

## 6. Mapa do projeto

```
sigae/
├── iniciar.ps1          ← liga o sistema
├── db.sqlite3           ← o banco (aparece depois da 1ª execução)
├── manage.py
├── config/              ← configurações do Django (settings.py, urls.py)
├── core/
│   ├── models.py        ← tabelas: User, Turma, Equipamento, Reserva
│   ├── services.py      ← regras: reservar, solicitar, entregar, devolver, cancelar
│   ├── views.py         ← telas (Início, Reservas, Equipamentos, Empréstimos...)
│   ├── forms.py · urls.py · admin.py
│   ├── management/commands/   ← seed.py e seed_demo.py (dados iniciais)
│   ├── migrations/      ← histórico das tabelas
│   └── templates/core/  ← páginas HTML
├── templates/base.html  ← menu lateral e layout
└── static/css/sigae.css ← cores e estilo
```

---

## 7. Planos futuros (anotações)

- Integrar uma base com **turmas, professores e acervo de notebooks**.
- **Perfis Professor e Aluno**: passam a ser apenas com o nome deles de acordo com a base de dados.
- 
- 