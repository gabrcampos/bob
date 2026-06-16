from modulos.db import listar_agenda

agenda = listar_agenda(empresa_id="fs_negao", status="pendente")
print(f"{len(agenda)} agendamentos pendentes:")
for a in agenda:
    print(f"  {a['data_hora'].strftime('%d/%m %H:%M')} UTC | {a['source_id']}")
