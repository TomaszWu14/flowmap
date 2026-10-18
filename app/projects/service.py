from ..ai import templates
from ..extensions import db
from ..flow import graph as g
from ..models import Project


def create_project(owner, name: str, start_sentence: str, mode: str, template_choice: str = "auto") -> Project:
    if template_choice == "auto":
        template = templates.match_template(start_sentence)
    else:
        template = template_choice if template_choice in templates.TEMPLATES else None
    project = Project(owner=owner, name=name.strip(), start_sentence=start_sentence.strip(),
                      mode=mode if mode in ("quick", "thorough") else "quick", template=template)
    db.session.add(project)
    db.session.flush()
    actor = templates.TEMPLATES[template]["start_actor"] if template else "Użytkownik"
    g.add_node(project, "start", project.start_sentence, actor, data={"tpl": "start"} if template else {})
    g.save_version(project, "Utworzono projekt")
    db.session.commit()
    return project


def project_from_graph(owner, name: str, start_sentence: str, mode: str, template: str | None,
                       graph: dict, note: str) -> Project:
    project = Project(owner=owner, name=name[:200], start_sentence=start_sentence[:500],
                      mode=mode if mode in ("quick", "thorough") else "quick",
                      template=template if template in templates.TEMPLATES else None)
    db.session.add(project)
    db.session.flush()
    g.load_graph(project, graph)
    g.save_version(project, note)
    db.session.commit()
    return project


def copy_project(project: Project, owner) -> Project:
    return project_from_graph(owner, f"{project.name} (kopia)", project.start_sentence, project.mode,
                              project.template, project.graph(), "Kopia projektu")
