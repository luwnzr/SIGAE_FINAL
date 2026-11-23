"""Regras de negócio. Toda alteração de estoque passa por transações com row-lock."""
import uuid

from django.db import transaction
from django.utils import timezone

from .models import Equipamento, Reserva

S, R = Equipamento.Status, Reserva.Status
STATUS_OCUPADOS = [R.PENDENTE, R.APROVADA, R.ATIVA, R.SOLICITADO_CANCELAMENTO]


class ReservaError(Exception):
    pass


def notebooks_disponiveis_qs(data, turno):
    """Retorna queryset dos notebooks livres naquela data e turno específicos."""
    ocupados_ids = (
        Reserva.objects.filter(data=data, turno=turno, status__in=STATUS_OCUPADOS)
        .exclude(equipamento__isnull=True)
        .values_list("equipamento_id", flat=True)
    )
    qs = Equipamento.objects.exclude(status=S.MANUTENCAO).exclude(pk__in=ocupados_ids)
    # Se for hoje, também exclui aparelhos atualmente emprestados em mãos de algum aluno
    if data == timezone.localdate():
        qs = qs.exclude(status=S.EMPRESTADO)
    return qs.order_by("numero")


@transaction.atomic
def criar_reservas(solicitante, data, turno, quantidade, turma=None):
    """Reserva (feita pelo instrutor para a turma) de 1 ou N notebooks por data/turno."""
    if turma and Reserva.objects.filter(turma=turma, data=data, turno=turno, status__in=STATUS_OCUPADOS).exists():
        raise ReservaError(f"A turma {turma.nome} já possui uma reserva para {data:%d/%m/%Y}.")

    notebooks = list(notebooks_disponiveis_qs(data, turno).select_for_update()[:quantidade])
    if len(notebooks) < quantidade:
        raise ReservaError(f"Só há {len(notebooks)} notebook(s) disponível(is) para {data:%d/%m/%Y} ({turno}); você pediu {quantidade}.")

    if data == timezone.localdate():
        Equipamento.objects.filter(pk__in=[n.pk for n in notebooks]).update(status=S.RESERVADO)

    lote = uuid.uuid4()
    return Reserva.objects.bulk_create([
        Reserva(
            solicitante=solicitante,
            turma=turma,
            equipamento=n,
            data=data,
            turno=turno,
            quantidade=quantidade,
            lote=lote,
            status=R.PENDENTE,
        )
        for n in notebooks
    ])


@transaction.atomic
def entregar(reserva_id, numero, admin):
    reserva = Reserva.objects.select_for_update().select_related("equipamento").get(pk=reserva_id)
    if not reserva.aguardando_entrega:
        raise ReservaError("Esta reserva não está aguardando entrega.")
    try:
        novo = Equipamento.objects.select_for_update().get(numero=numero)
    except Equipamento.DoesNotExist:
        raise ReservaError(f"Notebook {numero} não existe.")

    atual = reserva.equipamento
    if atual is None or atual.pk != novo.pk:
        if novo.status in (S.EMPRESTADO, S.MANUTENCAO):
            raise ReservaError(f"{novo} não está disponível ({novo.get_status_display()}).")
        if atual and atual.status == S.RESERVADO:
            Equipamento.objects.filter(pk=atual.pk).update(status=S.DISPONIVEL)

    novo.status = S.EMPRESTADO
    novo.save(update_fields=["status"])
    reserva.equipamento, reserva.status = novo, R.ATIVA
    reserva.entregue_em, reserva.entregue_por = timezone.now(), admin
    reserva.save()
    return reserva


@transaction.atomic
def devolver(reserva_id):
    reserva = Reserva.objects.select_for_update().select_related("equipamento").get(pk=reserva_id)
    if not reserva.esta_ativa:
        raise ReservaError("Esta reserva não está com equipamento entregue.")
    Equipamento.objects.filter(pk=reserva.equipamento_id).update(status=S.DISPONIVEL)
    reserva.status, reserva.devolvida_em = R.CONCLUIDA, timezone.now()
    reserva.save(update_fields=["status", "devolvida_em"])
    return reserva


@transaction.atomic
def solicitar_cancelamento_lote(reserva_id, instrutor):
    """O instrutor solicita o cancelamento do lote; aguarda autorização do Administrador."""
    alvo = Reserva.objects.select_for_update().get(pk=reserva_id)
    if alvo.solicitante_id != instrutor.pk:
        raise ReservaError("Você não pode solicitar o cancelamento desta reserva.")

    qs = Reserva.objects.select_for_update().filter(lote=alvo.lote) if alvo.lote else Reserva.objects.select_for_update().filter(pk=alvo.pk)
    pendentes = list(qs.filter(status__in=[R.PENDENTE, R.APROVADA]))
    if not pendentes:
        raise ReservaError("Não há itens aguardando entrega neste lote para cancelar.")

    Reserva.objects.filter(pk__in=[r.pk for r in pendentes]).update(status=R.SOLICITADO_CANCELAMENTO)
    return len(pendentes)


@transaction.atomic
def responder_cancelamento_lote(reserva_id, admin, aprovar=True):
    """O Administrador autoriza (libera notebooks) ou recusa o pedido de cancelamento."""
    if not admin.is_administrador:
        raise ReservaError("Apenas o Administrador pode autorizar ou recusar cancelamentos.")

    alvo = Reserva.objects.select_for_update().get(pk=reserva_id)
    qs = Reserva.objects.select_for_update().filter(lote=alvo.lote) if alvo.lote else Reserva.objects.select_for_update().filter(pk=alvo.pk)
    solicitados = list(qs.filter(status=R.SOLICITADO_CANCELAMENTO))
    if not solicitados:
        raise ReservaError("Não há solicitação de cancelamento pendente para esta reserva.")

    ids_reservas = [r.pk for r in solicitados]
    ids_equipamentos = [r.equipamento_id for r in solicitados if r.equipamento_id]

    if aprovar:
        Reserva.objects.filter(pk__in=ids_reservas).update(status=R.CANCELADA)
        if ids_equipamentos:
            Equipamento.objects.filter(pk__in=ids_equipamentos, status=S.RESERVADO).update(status=S.DISPONIVEL)
    else:
        Reserva.objects.filter(pk__in=ids_reservas).update(status=R.PENDENTE)
    return len(solicitados)


@transaction.atomic
def cancelar(reserva_id, usuario):
    """Cancelamento direto (usado pelo Administrador em um item ou lote)."""
    reserva = Reserva.objects.select_for_update().get(pk=reserva_id)
    if not usuario.is_administrador:
        raise ReservaError("Instrutores devem usar a opção 'Solicitar Cancelamento'.")
    if reserva.status not in (R.PENDENTE, R.APROVADA, R.SOLICITADO_CANCELAMENTO):
        raise ReservaError("Só é possível cancelar reservas que ainda não foram entregues.")
    if reserva.equipamento_id:
        Equipamento.objects.filter(pk=reserva.equipamento_id, status=S.RESERVADO).update(status=S.DISPONIVEL)
    reserva.status = R.CANCELADA
    reserva.save(update_fields=["status"])
    return reserva


@transaction.atomic
def resgatar(aluno, data):
    """O aluno 'recolhe' um dos notebooks que o instrutor reservou para a turma dele."""
    from .models import User
    aluno = User.objects.select_for_update().get(pk=aluno.pk)
    if not aluno.turma_id:
        raise ReservaError("Você não está vinculado a nenhuma turma.")
    if Reserva.objects.filter(aluno=aluno, data=data, status__in=[R.PENDENTE, R.APROVADA, R.ATIVA]).exists():
        raise ReservaError("Você já resgatou um notebook para hoje.")
    livre = (Reserva.objects.select_for_update()
             .filter(turma_id=aluno.turma_id, data=data, aluno__isnull=True, status__in=[R.PENDENTE, R.APROVADA])
             .order_by("equipamento__numero").first())
    if livre is None:
        raise ReservaError("Não há notebook reservado disponível para a sua turma hoje.")
    livre.aluno = aluno
    livre.save(update_fields=["aluno"])
    return livre

@transaction.atomic
def cancelar_resgate_aluno(reserva_id, aluno):
    """O aluno desiste da solicitação antes de retirar o notebook; devolve a vaga para o lote da turma."""
    reserva = Reserva.objects.select_for_update().get(pk=reserva_id)
    if reserva.aluno_id != aluno.pk:
        raise ReservaError("Você não pode cancelar a solicitação de outro aluno.")
    if not reserva.aguardando_entrega:
        raise ReservaError("Não é possível cancelar pois o notebook já foi entregue ou encerrado.")
    reserva.aluno = None
    reserva.save(update_fields=["aluno"])
    return reserva