from datetime import date
from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import PasswordChangeView
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import services
from .forms import EmprestimoFiltroForm, ReservaFiltroForm, ReservaForm, SenhaForm
from .models import Equipamento, Reserva, Turma, Turno

S, R = Equipamento.Status, Reserva.Status
ORDEM_TURNOS = [Turno.MATUTINO, Turno.VESPERTINO, Turno.NOTURNO]


def role_required(*roles):
    """roles: 'administrador', 'instrutor', 'aluno'."""
    def deco(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if not any(getattr(request.user, f"is_{r}") for r in roles):
                raise PermissionDenied
            return view(request, *args, **kwargs)
        return login_required(wrapper)
    return deco


def _reservas_visiveis(user):
    """Admin: tudo. Instrutor: o que ele reservou. Aluno: só o notebook que ele resgatou."""
    qs = Reserva.objects.select_related("solicitante", "equipamento", "turma", "aluno", "entregue_por")
    if user.is_administrador:
        return qs
    if user.is_instrutor:
        return qs.filter(solicitante=user)
    return qs.filter(aluno=user)


def _turno_atual(agora):
    h = agora.hour
    return Turno.MATUTINO if h < 12 else Turno.VESPERTINO if h < 18 else Turno.NOTURNO


def _estado(turno, agora, data=None):
    """encerrado (já passou) / atual / proximo — considera a data quando informada."""
    if data and data < agora.date():
        return "encerrado"
    if data and data > agora.date():
        return "proximo"
    i, a = ORDEM_TURNOS.index(turno), ORDEM_TURNOS.index(_turno_atual(agora))
    return "encerrado" if i < a else "atual" if i == a else "proximo"


def _agrupar_em_cards(reservas, agora, mostrar_data=False):
    """Reservas do mesmo lote viram um único cartão."""
    cards, n = {}, 0
    for r in reservas:
        chave = r.lote or f"r{r.pk}"
        if chave not in cards:
            n += 1
            cards[chave] = {
                "dom_id": f"grp{n}",
                "primeira_pk": r.pk,
                "solicitante": r.solicitante,
                "turma": r.turma,
                "data": r.data,
                "turno_label": r.get_turno_display(),
                "estado": _estado(r.turno, agora, r.data),
                "mostrar_data": mostrar_data,
                "reservas": [],
            }
        cards[chave]["reservas"].append(r)
    for c in cards.values():
        c["reservas"].sort(key=lambda r: r.equipamento.numero if r.equipamento_id else 0)
        c["resgatados"] = sum(1 for r in c["reservas"] if r.aluno_id)
        c["tem_aguardando"] = any(r.aguardando_entrega for r in c["reservas"])
        c["cancelamento_solicitado"] = any(r.cancelamento_pendente for r in c["reservas"])
    return list(cards.values())


# ---------- Início (Dashboard) ----------
@login_required
def dashboard(request):
    agora = timezone.localtime()
    hoje = agora.date()
    u = request.user

    if not (u.is_administrador or u.is_instrutor):
        ctx = {"hoje": hoje, "modo_aluno": True, "turma": u.turma}
        if u.turma_id:
            base = Reserva.objects.filter(turma_id=u.turma_id, data=hoje).exclude(status=R.CANCELADA)
            ctx["meu"] = base.filter(aluno=u).select_related("equipamento").first()
            ctx["livres"] = base.filter(aluno__isnull=True, status__in=[R.PENDENTE, R.APROVADA]).count()
            ctx["estado"] = _estado(u.turma.turno, agora)
        return render(request, "core/dashboard.html", ctx)

    reservas = list(_reservas_visiveis(u).filter(data=hoje).exclude(status=R.CANCELADA))
    reservas.sort(key=lambda r: ORDEM_TURNOS.index(r.turno))
    cards = _agrupar_em_cards(reservas, agora)

    cancelamentos_pendentes = 0
    if u.is_administrador:
        pendentes_qs = Reserva.objects.filter(status=R.SOLICITADO_CANCELAMENTO)
        cancelamentos_pendentes = len(_agrupar_em_cards(list(pendentes_qs), agora))

    return render(request, "core/dashboard.html", {
        "hoje": hoje,
        "cards": cards,
        "total": len(cards),
        "pode_reservar": u.is_instrutor,
        "cancelamentos_pendentes": cancelamentos_pendentes,
    })


# ---------- Equipamentos ----------
@login_required
def equipamentos(request):
    hoje = timezone.localdate()
    filtro = request.GET.get("status", "")
    notebooks = list(Equipamento.objects.filter(status=filtro) if filtro in S.values else Equipamento.objects.all())

    if request.user.is_administrador:
        em_uso = Reserva.objects.filter(
            equipamento__in=notebooks,
            data__gte=hoje,
            status__in=[R.PENDENTE, R.APROVADA, R.ATIVA, R.SOLICITADO_CANCELAMENTO],
        ).select_related("solicitante", "aluno", "turma").order_by("data", "turno")
        por_nb = {}
        for r in em_uso:
            por_nb.setdefault(r.equipamento_id, r)
        for n in notebooks:
            n.reserva_atual = por_nb.get(n.pk)

    minhas_turmas = []
    disponiveis_inicial = 0
    if request.user.is_instrutor:
        minhas_turmas = list(
            Turma.objects.filter(instrutor=request.user).prefetch_related("alunos")
        )
        minhas_turmas.sort(key=lambda t: (ORDEM_TURNOS.index(t.turno), t.nome))
        for t in minhas_turmas:
            t.total_alunos = t.alunos.count()
        if minhas_turmas:
            disponiveis_inicial = services.notebooks_disponiveis_qs(hoje, minhas_turmas[0].turno).count()

    return render(request, "core/equipamentos.html", {
        "notebooks": notebooks,
        "filtro": filtro,
        "status_choices": S.choices,
        "form": ReservaForm(),
        "pode_reservar": request.user.is_instrutor,
        "minhas_turmas": minhas_turmas,
        "hoje": hoje,
        "hoje_iso": hoje.isoformat(),
        "disponiveis_inicial": disponiveis_inicial,
    })


@require_POST
@role_required("administrador")
def alternar_manutencao_view(request, pk):
    eq = Equipamento.objects.filter(pk=pk).first()
    if not eq:
        messages.error(request, "Equipamento não encontrado.")
        return redirect("equipamentos")
    if eq.status == S.EMPRESTADO:
        messages.error(request, f"Patrimônio {eq.numero} está emprestado no momento; registre a devolução antes.")
        return redirect("equipamentos")
    if eq.status == S.MANUTENCAO:
        eq.status = S.DISPONIVEL
        eq.save(update_fields=["status"])
        messages.success(request, f"Patrimônio {eq.numero} liberado e marcado como Disponível.")
    else:
        eq.status = S.MANUTENCAO
        eq.save(update_fields=["status"])
        messages.warning(request, f"Patrimônio {eq.numero} enviado para Manutenção.")
    return redirect("equipamentos")


@login_required
def disponibilidade_json(request):
    """Retorna quantos notebooks estão disponíveis para a data e turno escolhidos."""
    data_str = request.GET.get("data", "")
    turno = request.GET.get("turno", "")
    try:
        data_obj = date.fromisoformat(data_str)
    except ValueError:
        data_obj = timezone.localdate()

    if turno not in Turno.values:
        return JsonResponse({"disponiveis": 0})

    qtd = services.notebooks_disponiveis_qs(data_obj, turno).count()
    return JsonResponse({"disponiveis": qtd})


@require_POST
@role_required("instrutor")
def reservar(request):
    """O instrutor seleciona uma de suas turmas e reserva até 1 notebook por aluno (sem duplicidade na mesma data)."""
    form = ReservaForm(request.POST)
    if not form.is_valid():
        messages.error(request, "; ".join(e for errs in form.errors.values() for e in errs))
        return redirect("equipamentos")

    d = form.cleaned_data
    turma_id = request.POST.get("turma_id")

    if turma_id:
        turma = Turma.objects.filter(pk=turma_id, instrutor=request.user).first()
    else:
        turma = Turma.objects.filter(instrutor=request.user, turno=d["turno"]).first()

    if turma is None:
        messages.error(request, "Selecione uma turma válida sob sua responsabilidade.")
        return redirect("equipamentos")

    total_alunos = turma.alunos.count()
    if total_alunos == 0:
        messages.error(request, f"A turma {turma.nome} não possui alunos matriculados para reservar notebooks.")
        return redirect("equipamentos")

    if d["quantidade"] > total_alunos:
        messages.error(
            request,
            f"Quantidade excedida: a turma {turma.nome} possui {total_alunos} aluno(s) (limite máximo de {total_alunos} notebook(s)).",
        )
        return redirect("equipamentos")

    ja_reservado = Reserva.objects.filter(
        turma=turma,
        data=d["data"],
        turno=turma.turno,
    ).exclude(status=R.CANCELADA).exists()

    if ja_reservado:
        messages.warning(
            request,
            f"A turma {turma.nome} já possui uma reserva para {d['data']:%d/%m/%Y} ({turma.get_turno_display()}).",
        )
        return redirect("dashboard")

    try:
        services.criar_reservas(request.user, d["data"], turma.turno, d["quantidade"], turma)
        messages.success(
            request,
            f"{d['quantidade']} notebook(s) reservado(s) para {turma.nome} ({turma.get_turno_display()}) em {d['data']:%d/%m/%Y}.",
        )
        return redirect("dashboard")
    except services.ReservaError as e:
        messages.error(request, str(e))
    return redirect("equipamentos")


@require_POST
@role_required("aluno")
def resgatar_view(request):
    try:
        r = services.resgatar(request.user, timezone.localdate())
        messages.success(request, f"Patrimônio {r.equipamento.numero} solicitado! Apresente-se ao Administrador para retirar.")
    except services.ReservaError as e:
        messages.error(request, str(e))
    return redirect("dashboard")


@require_POST
@role_required("aluno")
def cancelar_resgate_view(request, pk):
    try:
        services.cancelar_resgate_aluno(pk, request.user)
        messages.success(request, "Solicitação cancelada. O notebook voltou a ficar disponível para a turma.")
    except services.ReservaError as e:
        messages.error(request, str(e))
    return redirect("dashboard")


# ---------- Ações do Administrador e Solicitação de Cancelamento ----------
def _voltar(request):
    destino = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(destino, allowed_hosts={request.get_host()}):
        destino = "dashboard"
    return redirect(destino)


def _acao(request, fn, ok_msg, *args):
    try:
        fn(*args)
        messages.success(request, ok_msg)
    except services.ReservaError as e:
        messages.error(request, str(e))
    return _voltar(request)


@require_POST
@role_required("administrador")
def entregar_view(request, pk):
    try:
        numero = int(request.POST.get("numero", ""))
    except ValueError:
        messages.error(request, "Informe o patrimônio do notebook.")
        return _voltar(request)
    return _acao(request, services.entregar, f"Patrimônio {numero} entregue.", pk, numero, request.user)


@require_POST
@role_required("administrador")
def devolver_view(request, pk):
    return _acao(request, services.devolver, "Devolução registrada.", pk)


@require_POST
@role_required("administrador")
def cancelar_view(request, pk):
    return _acao(request, services.cancelar, "Reserva cancelada.", pk, request.user)


@require_POST
@role_required("instrutor")
def solicitar_cancelamento_view(request, pk):
    return _acao(
        request,
        services.solicitar_cancelamento_lote,
        "Solicitação de cancelamento enviada ao Administrador.",
        pk,
        request.user,
    )


@require_POST
@role_required("administrador")
def responder_cancelamento_view(request, pk):
    aprovar = request.POST.get("decisao") == "aprovar"
    msg = "Cancelamento autorizado e notebooks liberados." if aprovar else "Solicitação de cancelamento recusada; reserva mantida."
    return _acao(request, services.responder_cancelamento_lote, msg, pk, request.user, aprovar)


# ---------- Reservas (cartões + filtros) ----------
@login_required
def reservas(request):
    hoje = timezone.localdate()
    dados_filtro = request.GET.copy()

    # Se abriu a tela sem nenhum filtro na URL, assume a data de hoje por padrão
    if not request.GET:
        dados_filtro["data"] = hoje.isoformat()

    form = ReservaFiltroForm(dados_filtro)
    qs = _reservas_visiveis(request.user)
    if form.is_valid():
        d = form.cleaned_data
        if d["data"]:
            qs = qs.filter(data=d["data"])
        if d["turno"]:
            qs = qs.filter(turno=d["turno"])
        if d["equipamento"]:
            qs = qs.filter(equipamento__numero=d["equipamento"])
        if d["status"]:
            qs = qs.filter(status=d["status"])
    cards = _agrupar_em_cards(list(qs[:300]), timezone.localtime(), mostrar_data=True)
    return render(request, "core/reservas.html", {"form": form, "cards": cards})


# ---------- Empréstimos: Ver todos / Solicitações / Ativos ----------
def _pagina_emprestimos(request, titulo, qs, com_status=False):
    form = EmprestimoFiltroForm(request.GET or None)
    if form.is_valid():
        d = form.cleaned_data
        if d["codigo"]:
            qs = qs.filter(pk=d["codigo"])
        if d["data"]:
            qs = qs.filter(data=d["data"])
        if d["turno"]:
            qs = qs.filter(turno=d["turno"])
        if d["equipamento"]:
            qs = qs.filter(equipamento__numero=d["equipamento"])
        if com_status and d["status"]:
            qs = qs.filter(status=d["status"])
    mais_aberto = any(request.GET.get(k) for k in ("data", "turno", "equipamento", "status"))
    return render(request, "core/emprestimos.html", {
        "titulo": titulo,
        "form": form,
        "com_status": com_status,
        "mais_aberto": mais_aberto,
        "reservas": list(qs[:200]),
    })


@login_required
def emprestimos(request):
    hoje = timezone.localdate()
    dados_filtro = request.GET.copy()
    if not request.GET:
        dados_filtro["data"] = hoje.isoformat()
        request.GET = dados_filtro
    qs = _reservas_visiveis(request.user).filter(Q(aluno__isnull=False) | Q(entregue_em__isnull=False))
    return _pagina_emprestimos(request, "Todos os Empréstimos", qs.order_by("-data", "-criada_em"), com_status=True)


@login_required
def solicitacoes(request):
    qs = _reservas_visiveis(request.user).filter(aluno__isnull=False, status__in=[R.PENDENTE, R.APROVADA])
    return _pagina_emprestimos(request, "Solicitações", qs.order_by("data", "criada_em"))


@login_required
def ativos(request):
    qs = _reservas_visiveis(request.user).filter(status=R.ATIVA)
    return _pagina_emprestimos(request, "Empréstimos Ativos", qs.order_by("-entregue_em"))


# ---------- Turmas / Perfil ----------
@login_required
def turmas(request):
    u = request.user
    qs = Turma.objects.select_related("instrutor").prefetch_related("alunos")

    if u.is_administrador:
        lista = list(qs.all())
    elif u.is_instrutor:
        lista = list(qs.filter(instrutor=u))
    else:
        lista = list(qs.filter(pk=u.turma_id)) if u.turma_id else []

    lista.sort(key=lambda t: (ORDEM_TURNOS.index(t.turno), t.nome))
    return render(request, "core/turmas.html", {"turmas": lista})


class PerfilView(PasswordChangeView):
    template_name = "core/perfil.html"
    form_class = SenhaForm
    success_url = reverse_lazy("perfil")

    def form_valid(self, form):
        messages.success(self.request, "Senha alterada com sucesso.")
        return super().form_valid(form)