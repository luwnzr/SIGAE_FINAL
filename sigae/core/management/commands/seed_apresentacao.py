import random
import unicodedata
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from core.models import Turma, Turno, User


def limpar_texto(texto):
    normalizado = unicodedata.normalize("NFKD", texto).encode("ASCII", "ignore").decode("ASCII")
    return normalizado.lower().replace(" ", "")


class Command(BaseCommand):
    help = "Limpa exemplos antigos, redefine senhas e gera credenciais no usuarios_sigae.md."

    def handle(self, *args, **options):
        senha_padrao = "sigae@2026"

        grupo_admin, _ = Group.objects.get_or_create(name=User.GRUPO_ADMIN)
        grupo_instrutor, _ = Group.objects.get_or_create(name=User.GRUPO_INSTRUTOR)
        grupo_aluno, _ = Group.objects.get_or_create(name=User.GRUPO_ALUNO)

        usuarios_manter = {"admin.sigae", "carlos.mendes", "fernanda.rocha"}
        User.objects.exclude(username__in=usuarios_manter).delete()

        admin_user, _ = User.objects.update_or_create(
            username="admin.sigae",
            defaults={
                "first_name": "Administrador",
                "last_name": "SIGAE",
                "email": "admin.ti@df.senac.br",
                "is_staff": True,
                "is_superuser": True,
                "is_active": True,
            },
        )
        admin_user.set_password(senha_padrao)
        admin_user.save()
        admin_user.groups.set([grupo_admin])

        dados_instrutores = [
            {
                "username": "carlos.mendes",
                "first_name": "Carlos",
                "last_name": "Eduardo Mendes",
                "email": "carlos.mendes@df.senac.br",
                "turno": Turno.MATUTINO,
            },
            {
                "username": "fernanda.rocha",
                "first_name": "Fernanda",
                "last_name": "Alves Rocha",
                "email": "fernanda.rocha@df.senac.br",
                "turno": Turno.NOTURNO,
            },
        ]

        instrutores = []
        for inst in dados_instrutores:
            user, _ = User.objects.update_or_create(
                username=inst["username"],
                defaults={
                    "first_name": inst["first_name"],
                    "last_name": inst["last_name"],
                    "email": inst["email"],
                    "turno": inst["turno"],
                    "is_active": True,
                },
            )
            user.set_password(senha_padrao)
            user.save()
            user.groups.set([grupo_instrutor])
            instrutores.append(user)

        nomes_turmas_oficiais = [
            "Técnico em Administração",
            "Técnico em Secretariado",
            "Técnico em Análise e Desenvolvimento de Sistemas",
        ]
        Turma.objects.exclude(nome__in=nomes_turmas_oficiais).delete()

        dados_turmas = [
            {"nome": "Técnico em Administração", "turno": Turno.MATUTINO, "instrutor": instrutores[0], "qtd_alunos": 21},
            {"nome": "Técnico em Secretariado", "turno": Turno.VESPERTINO, "instrutor": instrutores[0], "qtd_alunos": 20},
            {"nome": "Técnico em Análise e Desenvolvimento de Sistemas", "turno": Turno.NOTURNO, "instrutor": instrutores[1], "qtd_alunos": 25},
        ]

        primeiros_nomes = [
            "Lucas", "Mariana", "Gabriel", "Beatriz", "Matheus", "Camila", "Rafael", "Larissa",
            "Pedro", "Amanda", "Gustavo", "Juliana", "Felipe", "Letícia", "Thiago", "Bianca",
            "João", "Isabela", "Bruno", "Natália", "Vinícius", "Carolina", "Diego", "Fernanda",
            "André", "Gabriela", "Rodrigo", "Aline", "Eduardo", "Vitória", "Caio", "Lívia",
            "Igor", "Sofia", "Daniel", "Helena", "Renan", "Laura", "Henrique", "Clara",
        ]
        sobrenomes = [
            "Silva", "Santos", "Oliveira", "Souza", "Rodrigues", "Ferreira", "Alves", "Pereira",
            "Lima", "Gomes", "Costa", "Ribeiro", "Martins", "Carvalho", "Almeida", "Lopes",
            "Soares", "Fernandes", "Vieira", "Barbosa", "Rocha", "Dias", "Nascimento", "Moreira",
        ]

        logins_usados = set(usuarios_manter)
        alunos_teste_por_turno = []

        for t_info in dados_turmas:
            turma, _ = Turma.objects.update_or_create(
                nome=t_info["nome"],
                turno=t_info["turno"],
                defaults={"instrutor": t_info["instrutor"]},
            )

            alunos_da_turma = []
            for _ in range(t_info["qtd_alunos"]):
                while True:
                    p_nome = random.choice(primeiros_nomes)
                    s_nome_principal = random.choice(sobrenomes)
                    s_nome_segundo = random.choice([s for s in sobrenomes if s != s_nome_principal])

                    login_base = f"{limpar_texto(p_nome)}{limpar_texto(s_nome_principal)}"
                    if login_base not in logins_usados:
                        logins_usados.add(login_base)
                        break

                email = f"{login_base}@edu.df.senac.br"
                aluno = User.objects.create(
                    username=login_base,
                    first_name=p_nome,
                    last_name=f"{s_nome_principal} {s_nome_segundo}",
                    email=email,
                    turma=turma,
                    turno=t_info["turno"],
                    is_active=True,
                )
                aluno.set_password(senha_padrao)
                aluno.save()
                aluno.groups.add(grupo_aluno)
                alunos_da_turma.append(aluno)

            alunos_teste_por_turno.append(random.choice(alunos_da_turma))

        linhas = [
            "# Credenciais de Apresentação - SIGAE\n\n",
            f"**Senha padrão para todos os perfis:** `{senha_padrao}`\n\n",
            "## 1. Administrador (`@df.senac.br`)\n",
            f"- **{admin_user.nome_completo}** — Login: `{admin_user.username}` | E-mail: `{admin_user.email}`\n\n",
            "## 2. Instrutores (`@df.senac.br`)\n",
            f"- **{instrutores[0].nome_completo}** (Matutino e Vespertino) — Login: `{instrutores[0].username}` | E-mail: `{instrutores[0].email}`\n",
            f"- **{instrutores[1].nome_completo}** (Noturno) — Login: `{instrutores[1].username}` | E-mail: `{instrutores[1].email}`\n\n",
            "## 3. Alunos de Teste — 1 por Turno (`@edu.df.senac.br`)\n",
        ]
        for al in alunos_teste_por_turno:
            linhas.append(
                f"- **{al.turma.get_turno_display()}** ({al.turma.nome}) — **{al.nome_completo}** | "
                f"Login: `{al.username}` | E-mail: `{al.email}`\n"
            )

        with open("usuarios_sigae.md", "w", encoding="utf-8") as f:
            f.writelines(linhas)

        self.stdout.write(
            self.style.SUCCESS(
                "Banco limpo e atualizado! Admin, 2 Instrutores e 3 Alunos de teste salvos em usuarios_sigae.md."
            )
        )