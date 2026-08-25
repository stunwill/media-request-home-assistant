from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field

from . import auth, main, release_activity_ui

app = release_activity_ui.app
app.version = "0.6.10-dev"


class UserLoginUpdate(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    password: str = Field(min_length=12, max_length=1024)


def _user_row(db: sqlite3.Connection, user_id: str) -> sqlite3.Row | None:
    return db.execute(
        """
        SELECT id, username, display_name, role, active, created_at, updated_at,
               last_seen_at
        FROM users
        WHERE id = ?
        """,
        (user_id,),
    ).fetchone()


def _public_user(db: sqlite3.Connection, user_id: str) -> dict[str, Any] | None:
    row = _user_row(db, user_id)
    if row is None:
        return None
    credential = db.execute(
        "SELECT username_normalized FROM local_credentials WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    is_home_assistant = not str(row["id"]).startswith("local:")
    login_enabled = credential is not None
    if is_home_assistant and login_enabled:
        auth_source = "home_assistant_and_mediahub"
    elif is_home_assistant:
        auth_source = "home_assistant"
    else:
        auth_source = "mediahub"
    return {
        "id": str(row["id"]),
        "username": str(row["username"]),
        "display_name": str(row["display_name"]),
        "role": str(row["role"]),
        "active": bool(row["active"]),
        "auth_source": auth_source,
        "home_assistant_identity": is_home_assistant,
        "mediahub_login_enabled": login_enabled,
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
        "last_seen_at": str(row["last_seen_at"]),
    }


def get_users(_: main.Administrator) -> list[dict[str, Any]]:
    with main.connect_db() as db:
        rows = db.execute(
            "SELECT id FROM users ORDER BY display_name COLLATE NOCASE, id"
        ).fetchall()
        return [
            user
            for row in rows
            if (user := _public_user(db, str(row["id"]))) is not None
        ]


def set_mediahub_login(
    user_id: str,
    payload: UserLoginUpdate,
    principal: main.Administrator,
) -> dict[str, Any]:
    clean_username = " ".join(payload.username.replace("\x00", "").split()).strip()
    normalized = auth.normalise_username(clean_username)
    if len(normalized) < 3 or len(clean_username) > 100:
        raise HTTPException(status_code=422, detail="Username must contain 3 to 100 characters")

    now = main.utc_now()
    with main.connect_db() as db:
        row = _user_row(db, user_id)
        if row is None:
            raise HTTPException(status_code=404, detail="MediaHub user not found")

        collision = db.execute(
            """
            SELECT user_id FROM local_credentials
            WHERE username_normalized = ? AND user_id <> ?
            LIMIT 1
            """,
            (normalized, user_id),
        ).fetchone()
        if collision:
            raise HTTPException(status_code=409, detail="That MediaHub login username is already in use")

        password_hash = auth.hash_password(payload.password)
        existing = db.execute(
            "SELECT 1 FROM local_credentials WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if existing:
            db.execute(
                """
                UPDATE local_credentials
                SET username_normalized = ?, password_hash = ?, password_changed_at = ?
                WHERE user_id = ?
                """,
                (normalized, password_hash, now, user_id),
            )
            action = "mediahub_login_password_reset"
        else:
            db.execute(
                """
                INSERT INTO local_credentials (
                    user_id, username_normalized, password_hash, password_changed_at
                ) VALUES (?, ?, ?, ?)
                """,
                (user_id, normalized, password_hash, now),
            )
            action = "mediahub_login_enabled"

        # Keep the visible username aligned with the external login name. Home Assistant
        # can continue refreshing the account identity during ingress sessions.
        db.execute(
            "UPDATE users SET username = ?, updated_at = ? WHERE id = ?",
            (clean_username, now, user_id),
        )
        # A password change invalidates any existing MediaHub sessions for this account.
        db.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))
        main.record_audit(
            db,
            actor_id=principal.user_id,
            actor_name=principal.display_name,
            action=action,
            request_id=None,
            details={"user_id": user_id, "username": clean_username},
        )
        db.commit()
        result = _public_user(db, user_id)

    if result is None:
        raise HTTPException(status_code=404, detail="MediaHub user not found")
    return result


# Replace the Users list so it can represent dual-auth accounts, and add one
# administrator-only credential endpoint. Existing Home Assistant login remains unchanged.
release_activity_ui.release_activity.enhanced_main._replace_route(
    "/api/users",
    "GET",
    get_users,
)
app.add_api_route(
    "/api/users/{user_id}/mediahub-login",
    set_mediahub_login,
    methods=["PUT"],
)


_DUAL_LOGIN_UI = r"""
<style>
  .credential-dialog{width:min(560px,100%)}
  .credential-body{padding:28px;display:grid;gap:16px}
  .credential-actions{display:flex;gap:10px;justify-content:flex-end;flex-wrap:wrap}
  @media(max-width:760px){.credential-body{padding:22px 20px}.credential-actions{display:grid}.credential-actions .button{width:100%}}
</style>
<div class="modal hidden" id="credential-modal" role="dialog" aria-modal="true" aria-labelledby="credential-title">
  <div class="dialog credential-dialog">
    <button class="close" id="close-credential-modal" aria-label="Close">✕</button>
    <form class="credential-body" id="credential-form">
      <div><div class="eyebrow">MediaHub login</div><h2 id="credential-title" style="margin:7px 0 6px">Enable MediaHub login</h2><div class="muted" id="credential-user"></div></div>
      <label class="field">Login username<input id="credential-username" autocomplete="username" minlength="3" maxlength="100" required></label>
      <label class="field">Password<input id="credential-password" type="password" autocomplete="new-password" minlength="12" maxlength="1024" required></label>
      <label class="field">Confirm password<input id="credential-confirm" type="password" autocomplete="new-password" minlength="12" maxlength="1024" required></label>
      <div class="hint">At least 12 characters. This creates a MediaHub password for external sign-in. Home Assistant sign-in continues to work as before.</div>
      <div class="message" id="credential-message"></div>
      <div class="credential-actions"><button class="button" type="button" id="cancel-credential">Cancel</button><button class="button primary" type="submit" id="save-credential">Save MediaHub login</button></div>
    </form>
  </div>
</div>
<script>
  let dualLoginUsers=[];
  let dualLoginSelected=null;

  function dualLoginSourceLabel(user){
    if(user.auth_source==='home_assistant_and_mediahub')return 'Home Assistant + MediaHub';
    if(user.auth_source==='home_assistant')return 'Home Assistant';
    return 'MediaHub login';
  }

  async function refreshDualLoginUsers(){
    if(!state.user||state.user.role!=='admin')return;
    try{
      dualLoginUsers=await api('users');
      decorateDualLoginUsers();
    }catch(_error){}
  }

  function decorateDualLoginUsers(){
    document.querySelectorAll('#user-list [data-user-id]').forEach(card=>{
      const user=dualLoginUsers.find(item=>item.id===card.dataset.userId);
      if(!user)return;
      const source=card.querySelector('.account-source');
      if(source)source.textContent=dualLoginSourceLabel(user);
      if(!user.home_assistant_identity)return;
      const controls=card.querySelector('.user-controls');
      if(!controls)return;
      let button=controls.querySelector('[data-mediahub-login]');
      if(!button){
        button=document.createElement('button');
        button.type='button';
        button.className='button';
        button.dataset.mediahubLogin='';
        controls.append(button);
      }
      button.textContent=user.mediahub_login_enabled?'Reset MediaHub password':'Enable MediaHub login';
      button.onclick=()=>openCredentialModal(user);
    });
  }

  function openCredentialModal(user){
    dualLoginSelected=user;
    document.getElementById('credential-title').textContent=user.mediahub_login_enabled?'Reset MediaHub password':'Enable MediaHub login';
    document.getElementById('credential-user').textContent=user.display_name;
    document.getElementById('credential-username').value=user.username||'';
    document.getElementById('credential-password').value='';
    document.getElementById('credential-confirm').value='';
    document.getElementById('credential-message').textContent='';
    document.getElementById('credential-modal').classList.remove('hidden');
    document.getElementById('credential-password').focus();
  }

  function closeCredentialModal(){
    document.getElementById('credential-modal').classList.add('hidden');
    dualLoginSelected=null;
  }

  document.getElementById('close-credential-modal').addEventListener('click',closeCredentialModal);
  document.getElementById('cancel-credential').addEventListener('click',closeCredentialModal);
  document.getElementById('credential-modal').addEventListener('click',event=>{if(event.target.id==='credential-modal')closeCredentialModal();});
  document.getElementById('credential-form').addEventListener('submit',async event=>{
    event.preventDefault();
    if(!dualLoginSelected)return;
    const username=document.getElementById('credential-username').value.trim();
    const password=document.getElementById('credential-password').value;
    const confirm=document.getElementById('credential-confirm').value;
    const message=document.getElementById('credential-message');
    const save=document.getElementById('save-credential');
    if(password!==confirm){message.textContent='Passwords do not match.';message.className='message error';return;}
    if(password.length<12){message.textContent='Password must contain at least 12 characters.';message.className='message error';return;}
    save.disabled=true;
    try{
      await api(`users/${encodeURIComponent(dualLoginSelected.id)}/mediahub-login`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({username,password})});
      closeCredentialModal();
      toast('MediaHub login saved');
      await loadUsers();
      await refreshDualLoginUsers();
    }catch(error){message.textContent=error.message;message.className='message error';}
    finally{save.disabled=false;}
  });

  const dualUserList=document.getElementById('user-list');
  if(dualUserList)new MutationObserver(()=>{queueMicrotask(decorateDualLoginUsers);}).observe(dualUserList,{childList:true,subtree:true});
  const dualUsersNav=document.getElementById('users-nav');
  if(dualUsersNav)dualUsersNav.addEventListener('click',()=>setTimeout(refreshDualLoginUsers,0));
  setTimeout(refreshDualLoginUsers,0);
</script>
"""

if "credential-modal" not in main.INDEX_HTML:
    main.INDEX_HTML = main.INDEX_HTML.replace("</body>", _DUAL_LOGIN_UI + "\n</body>")
