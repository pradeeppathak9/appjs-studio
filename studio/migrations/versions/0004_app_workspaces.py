"""apps become workspaces: templates belong to one app, per-app member roles

- users.role: admin | user (creator/tester become per-app roles)
- app_members(app_id, user_id, role editor|tester): every existing non-admin user joins every
  existing app, creators as editors and testers as testers
- templates.app_id (+ position, deleted_at): each template moves to the first app it was enabled
  in; templates in no app go to a new "Imported templates" app. Archived templates become deleted.
  Slugs are unique per app.
- app_templates is dropped; jobs and uploads get the app of their template where known
- apps.deleted_at

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("apps", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "app_members",
        sa.Column("app_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role IN ('editor','tester')", name=op.f("ck_app_members_role")),
        sa.ForeignKeyConstraint(
            ["app_id"], ["apps.id"], name=op.f("fk_app_members_app_id_apps"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_app_members_user_id_users"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("app_id", "user_id", name=op.f("pk_app_members")),
    )
    op.create_index(op.f("ix_app_members_user_id"), "app_members", ["user_id"], unique=False)

    op.add_column("templates", sa.Column("app_id", sa.UUID(), nullable=True))
    op.add_column("templates", sa.Column("position", sa.Integer(), server_default="0", nullable=False))
    op.add_column("templates", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("uploads", sa.Column("app_id", sa.UUID(), nullable=True))

    # ---- data ----------------------------------------------------------------------------------
    # first app (oldest) each template was enabled in, keeping its position there
    op.execute(
        """
        UPDATE templates t SET app_id = x.app_id, position = x.position
        FROM (
            SELECT DISTINCT ON (at.template_id) at.template_id, at.app_id, at.position
            FROM app_templates at JOIN apps a ON a.id = at.app_id
            ORDER BY at.template_id, a.created_at, at.position
        ) x
        WHERE x.template_id = t.id
        """
    )
    op.execute(
        """
        INSERT INTO apps (id, slug, name, description, platform, status, created_by)
        SELECT gen_random_uuid(), 'imported-templates', 'Imported templates',
               'Templates that were not enabled in any app when apps became workspaces.',
               'other', 'disabled', (SELECT created_by FROM templates WHERE app_id IS NULL
                                     ORDER BY created_at LIMIT 1)
        WHERE EXISTS (SELECT 1 FROM templates WHERE app_id IS NULL)
          AND NOT EXISTS (SELECT 1 FROM apps WHERE slug = 'imported-templates')
        """
    )
    op.execute(
        """
        UPDATE templates t SET app_id = (SELECT id FROM apps WHERE slug = 'imported-templates'),
               position = x.n
        FROM (SELECT id, row_number() OVER (ORDER BY created_at) AS n FROM templates WHERE app_id IS NULL) x
        WHERE x.id = t.id
        """
    )
    op.execute("UPDATE templates SET deleted_at = now(), status = 'draft' WHERE status = 'archived'")
    op.execute(
        """
        INSERT INTO app_members (app_id, user_id, role)
        SELECT a.id, u.id, CASE u.role WHEN 'creator' THEN 'editor' ELSE 'tester' END
        FROM apps a CROSS JOIN users u
        WHERE u.role IN ('creator', 'tester') AND u.deleted_at IS NULL
        """
    )
    op.execute(
        "UPDATE jobs j SET app_id = t.app_id FROM templates t WHERE j.template_id = t.id AND j.app_id IS NULL"
    )
    op.execute(
        """
        UPDATE uploads u SET app_id = t.app_id
        FROM template_versions v JOIN templates t ON t.id = v.template_id
        WHERE u.id = v.cover_upload OR u.id = ANY (v.reference_uploads)
        """
    )

    # ---- constraints -----------------------------------------------------------------------------
    op.drop_constraint(op.f("ck_users_role"), "users", type_="check")
    op.execute("UPDATE users SET role = 'user' WHERE role IN ('creator', 'tester')")
    op.create_check_constraint(op.f("ck_users_role"), "users", "role IN ('admin','user')")

    op.drop_constraint(op.f("ck_templates_status"), "templates", type_="check")
    op.create_check_constraint(op.f("ck_templates_status"), "templates", "status IN ('draft','active')")
    op.drop_constraint(op.f("uq_templates_slug"), "templates", type_="unique")
    op.alter_column("templates", "app_id", nullable=False)
    op.create_foreign_key(op.f("fk_templates_app_id_apps"), "templates", "apps", ["app_id"], ["id"])
    op.create_unique_constraint(op.f("uq_templates_app_id_slug"), "templates", ["app_id", "slug"])
    op.create_index("ix_templates_app_position", "templates", ["app_id", "position"], unique=False)
    op.create_foreign_key(op.f("fk_uploads_app_id_apps"), "uploads", "apps", ["app_id"], ["id"])

    op.drop_index(op.f("ix_app_templates_template_id"), table_name="app_templates")
    op.drop_table("app_templates")


def downgrade() -> None:
    op.create_table(
        "app_templates",
        sa.Column("app_id", sa.UUID(), nullable=False),
        sa.Column("template_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["app_id"], ["apps.id"], name=op.f("fk_app_templates_app_id_apps"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["template_id"],
            ["templates.id"],
            name=op.f("fk_app_templates_template_id_templates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("app_id", "template_id", name=op.f("pk_app_templates")),
    )
    op.create_index(op.f("ix_app_templates_template_id"), "app_templates", ["template_id"], unique=False)
    op.execute(
        "INSERT INTO app_templates (app_id, template_id, position) "
        "SELECT app_id, id, position FROM templates WHERE deleted_at IS NULL"
    )

    op.drop_constraint(op.f("fk_uploads_app_id_apps"), "uploads", type_="foreignkey")
    op.drop_index("ix_templates_app_position", table_name="templates")
    op.drop_constraint(op.f("uq_templates_app_id_slug"), "templates", type_="unique")
    op.drop_constraint(op.f("fk_templates_app_id_apps"), "templates", type_="foreignkey")
    # slugs were only unique per app; make them unique again before restoring the global constraint
    op.execute(
        """
        UPDATE templates t SET slug = left(t.slug, 55) || '-' || left(md5(t.id::text), 8)
        FROM (SELECT slug FROM templates GROUP BY slug HAVING count(*) > 1) d WHERE d.slug = t.slug
        """
    )
    op.create_unique_constraint(op.f("uq_templates_slug"), "templates", ["slug"])
    op.drop_constraint(op.f("ck_templates_status"), "templates", type_="check")
    op.execute("UPDATE templates SET status = 'archived' WHERE deleted_at IS NOT NULL")
    op.create_check_constraint(
        op.f("ck_templates_status"), "templates", "status IN ('draft','active','archived')"
    )

    op.drop_constraint(op.f("ck_users_role"), "users", type_="check")
    op.execute(
        """
        UPDATE users u SET role = CASE WHEN EXISTS (
            SELECT 1 FROM app_members m WHERE m.user_id = u.id AND m.role = 'editor') THEN 'creator'
            ELSE 'tester' END
        WHERE role = 'user'
        """
    )
    op.create_check_constraint(op.f("ck_users_role"), "users", "role IN ('admin','creator','tester')")

    op.drop_column("uploads", "app_id")
    op.drop_column("templates", "deleted_at")
    op.drop_column("templates", "position")
    op.drop_column("templates", "app_id")
    op.drop_index(op.f("ix_app_members_user_id"), table_name="app_members")
    op.drop_table("app_members")
    op.drop_column("apps", "deleted_at")
