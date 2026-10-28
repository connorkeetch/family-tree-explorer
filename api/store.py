"""Per-user tree persistence (DB-backed).

Every read/write is scoped to an owner id, so one user can never reach another's
tree (the query simply won't match). Tree ids are unguessable url-safe tokens.
"""
import secrets

from sqlalchemy.orm import Session

import core

from .models import Tree


def create_tree(db: Session, owner_id: int, people: list[dict],
                source_files: list[str] | None = None) -> dict:
    tree_id = secrets.token_urlsafe(9)
    meta = core.tree_meta(people)
    if source_files is not None:
        meta["source_files"] = source_files
    db.add(Tree(id=tree_id, owner_id=owner_id, meta=meta, people=people))
    db.commit()
    return {"id": tree_id, "meta": meta}


def get_people(db: Session, owner_id: int, tree_id: str) -> list[dict] | None:
    tree = db.get(Tree, tree_id)
    if tree is None or tree.owner_id != owner_id:
        return None
    return tree.people


def source_files(db: Session, owner_id: int, tree_id: str) -> dict:
    row = db.query(Tree.meta).filter(Tree.id == tree_id, Tree.owner_id == owner_id).first()
    return {"source_files": row.meta["source_files"]} if row and "source_files" in row.meta else {}


def list_trees(db: Session, owner_id: int) -> list[dict]:
    rows = (db.query(Tree.id, Tree.meta, Tree.created_at)
            .filter(Tree.owner_id == owner_id)
            .order_by(Tree.created_at.desc())
            .all())
    return [{"id": r.id, "meta": r.meta,
             "created_at": r.created_at.isoformat() if r.created_at else None}
            for r in rows]


def delete_tree(db: Session, owner_id: int, tree_id: str) -> bool:
    tree = db.get(Tree, tree_id)
    if tree is None or tree.owner_id != owner_id:
        return False
    db.delete(tree)
    db.commit()
    return True
