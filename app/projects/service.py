from ..ai import templates
from ..extensions import db
from ..flow import graph as g
from ..models import Project, UserTemplate


def create_project(owner, name: str, start_sentence: str, mode: str, template_choice: str = "auto") -> Project:
    if template_choice == "auto":
        template = templates.match_template(start_sentence, UserTemplate.query.filter_by(owner_id=owner.id).all())
    else:
        template = template_choice if templates.get(template_choice) else None
    project = Project(owner=owner, name=name.strip(), start_sentence=start_sentence.strip(),
                      mode=mode if mode in ("quick", "thorough") else "quick", template=template)
    db.session.add(project)
    db.session.flush()
    actor = templates.get(template)["start_actor"] if template else "Użytkownik"
    g.add_node(project, "start", project.start_sentence, actor,
               data={"tpl": templates.start_key(template)} if template else {})
    g.save_version(project, "Utworzono projekt")
    db.session.commit()
    return project


def _template_allowed(template: str | None, owner) -> bool:
    """Built-ins for everyone; a saved template only for its owner (imports cannot borrow others')."""
    if not template or not templates.get(template):
        return False
    if template.startswith(templates.USER_PREFIX):
        ut = db.session.get(UserTemplate, int(template[len(templates.USER_PREFIX):]))
        return ut is not None and ut.owner_id == owner.id
    return True


def project_from_graph(owner, name: str, start_sentence: str, mode: str, template: str | None,
                       graph: dict, note: str) -> Project:
    project = Project(owner=owner, name=name[:200], start_sentence=start_sentence[:500],
                      mode=mode if mode in ("quick", "thorough") else "quick",
                      template=template if _template_allowed(template, owner) else None)
    db.session.add(project)
    db.session.flush()
    g.load_graph(project, graph)
    g.save_version(project, note)
    db.session.commit()
    return project


def copy_project(project: Project, owner) -> Project:
    graph = project.graph()
    if project.spec is not None:
        graph = graph | {"spec": project.spec}
    copy = project_from_graph(owner, f"{project.name} (kopia)", project.start_sentence, project.mode,
                              project.template, graph, "Kopia projektu")
    copy.display = project.display  # swimlane order and icons travel with the copy
    return copy
