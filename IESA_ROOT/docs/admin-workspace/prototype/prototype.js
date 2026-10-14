(() => {
  "use strict";
  const main = document.getElementById("main"),
    persona = document.getElementById("persona");
  const posts = [
    {
      id: 1,
      title: "Безопасность на тренировках: что важно новичкам",
      author: "Анна Петрова",
      time: "Сегодня, 10:35",
      status: "pending",
    },
    {
      id: 2,
      title: "Встреча участников IESA в выходные",
      author: "Сергей Иванов",
      time: "Вчера, 18:20",
      status: "pending",
    },
    {
      id: 3,
      title: "Как подготовиться к первому турниру",
      author: "Мария Коваль",
      time: "Вчера, 15:10",
      status: "pending",
    },
  ];
  const team = [
    {
      name: "Мария Коваль",
      role: "Модератор сообщества",
      scope: "Всё сообщество",
      expires: "Без срока",
      active: true,
    },
    {
      name: "Алексей Смирнов",
      role: "Менеджер партнёров",
      scope: "Alpine Club",
      expires: "31 декабря 2026",
      active: true,
    },
  ];
  const roles = {
    moderator: {
      name: "Модератор сообщества",
      allowed: [
        "Проверять, публиковать и возвращать материалы",
        "Модерировать комментарии",
      ],
      denied: ["Контакты участников", "Экспорт данных", "Управление доступом"],
    },
    partners: {
      name: "Менеджер партнёров",
      allowed: [
        "Просматривать профиль назначенных организаций",
        "Корректировать и отменять визиты с причиной",
      ],
      denied: [
        "Чужие организации",
        "Закрытые документы",
        "Управление доступом",
      ],
    },
  };
  const history = [
    "Мария опубликовала материал «Спорт и сообщество»",
    "Выдана карта участника · Сергей Иванов",
  ];
  let draft = {
      person: "Мария Коваль",
      role: "moderator",
      scope: "Alpine Club",
      expiry: "2026-12-31",
      reason: "",
    },
    step = 1,
    pendingRevoke = null,
    nextNotice = "";
  const esc = (s) =>
    String(s).replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const status = (s) =>
    ({
      pending: "На проверке",
      published: "Опубликовано",
      returned: "Возвращено автору",
    })[s];
  const pending = () => posts.filter((p) => p.status === "pending").length;
  function notify(message) {
    const el = document.getElementById("notice");
    el.hidden = false;
    el.innerHTML = `${esc(message)}<button aria-label="Закрыть сообщение">×</button>`;
    el.querySelector("button").onclick = () => (el.hidden = true);
  }
  function head(title, sub, action = "") {
    return `<div class="page-head"><div><div class="eyebrow">УПРАВЛЕНИЕ IESA</div><h1>${title}</h1><p class="muted">${sub}</p></div>${action}</div>`;
  }
  function postRow(p) {
    return `<div class="row"><div class="row-main"><h3>${esc(p.title)}</h3><p class="muted">${esc(p.author)} · ${esc(p.time)}</p><div class="tags"><span class="tag ${p.status === "published" ? "success" : ""}">${status(p.status)}</span></div></div><a class="quiet" href="#review/${p.id}">${p.status === "pending" ? "Проверить" : "Открыть"}</a></div>`;
  }
  function render() {
    const route = location.hash.slice(1) || "overview";
    const owner = persona.value === "owner";
    document.body.classList.toggle(
      "review-active",
      route.startsWith("review/") &&
        posts.some(
          (p) => p.id === Number(route.split("/")[1]) && p.status === "pending",
        ),
    );
    document.getElementById("team-link").hidden = !owner;
    document.getElementById("account-label").textContent = owner
      ? "Владелец панели"
      : "Модератор сообщества";
    document.getElementById("nav-count").textContent = pending();
    document.querySelectorAll("[data-page]").forEach((a) => {
      const active =
        a.dataset.page ===
        (route.startsWith("review")
          ? "community"
          : route === "grant"
            ? "team"
            : route);
      a.classList.toggle("active", active);
      if (active) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    if (!owner && (route === "team" || route === "grant")) {
      location.hash = "community";
      return;
    }
    if (route === "overview") {
      main.innerHTML =
        head(
          owner ? "Что требует внимания" : "Мои задачи",
          owner
            ? "Все доступные очереди и последние решения команды."
            : "Материалы сообщества, которые ждут вашего решения.",
        ) +
        `<div class="grid"><section class="card"><i class="fas fa-file-lines" aria-hidden="true"></i><div class="number">${pending()}</div><p>Публикации на проверке</p><a class="quiet" href="#community">Открыть очередь</a></section>${owner ? `<section class="card"><i class="fas fa-user-shield" aria-hidden="true"></i><div class="number">${team.filter((t) => t.active).length}</div><p>Сотрудники с доступом</p><a class="quiet" href="#team">Управлять доступом</a></section>` : ""}</div><div class="two-column"><section class="panel"><h2>Начните с очереди</h2>${
          posts
            .filter((p) => p.status === "pending")
            .map(postRow)
            .join("") || "<p>Сейчас всё проверено.</p>"
        }</section><section class="panel"><h2>Последние действия</h2><ul class="history">${(owner ? history : history.filter((h) => h.toLowerCase().includes("публи") || h.startsWith("Возвращено"))).map((h) => `<li>${esc(h)}<small>Сегодня · демонстрация</small></li>`).join("")}</ul></section></div>`;
    } else if (route === "community") {
      main.innerHTML =
        head(
          "Сообщество",
          "Проверьте материал в том виде, в котором его увидит участник.",
        ) +
        `<div class="toolbar"><div class="field"><label for="search">Найти публикацию</label><input type="search" id="search" placeholder="Название или автор"></div><div class="field"><label for="status">Статус</label><select id="status"><option value="pending">На проверке</option><option value="all">Все материалы</option><option value="published">Опубликовано</option><option value="returned">Возвращено автору</option></select></div></div><section class="panel" id="post-list" aria-label="Публикации"></section>`;
      const filter = () => {
        const q = document.getElementById("search").value.toLowerCase(),
          s = document.getElementById("status").value;
        document.getElementById("post-list").innerHTML =
          posts
            .filter(
              (p) =>
                (s === "all" || p.status === s) &&
                (p.title + " " + p.author).toLowerCase().includes(q),
            )
            .map(postRow)
            .join("") ||
          '<div class="empty"><h2>Материалов не найдено</h2><p class="muted">Измените запрос или выберите другой статус.</p></div>';
      };
      document.getElementById("search").oninput = filter;
      document.getElementById("status").onchange = filter;
      filter();
    } else if (route.startsWith("review/")) {
      const p = posts.find((x) => x.id === Number(route.split("/")[1]));
      if (!p) {
        location.hash = "community";
        return;
      }
      main.innerHTML =
        `<a href="#community" class="back"><i class="fas fa-arrow-left" aria-hidden="true"></i>К очереди публикаций</a>` +
        head("Проверка публикации", `Материал №${p.id} · ${status(p.status)}`) +
        `<div class="two-column"><article class="panel article"><div class="eyebrow">СООБЩЕСТВО</div><h2>${esc(p.title)}</h2><p class="byline muted">${esc(p.author)} · ${esc(p.time)}</p><p>Начинать занятия проще, когда рядом люди, готовые поделиться опытом. Мы собрали несколько рекомендаций для новых участников IESA.</p><h3>Перед первой тренировкой</h3><p>Обсудите программу с тренером, проверьте экипировку и заранее уточните правила площадки. Постепенно увеличивайте нагрузку и оставляйте время на восстановление.</p><p>На встрече сообщества можно задать вопросы опытным участникам и найти подходящую группу для занятий.</p></article><section class="panel decision"><h2>Ваше решение</h2><p class="muted">${p.status === "pending" ? "Публикация появится на сайте после одобрения. Если нужны исправления, объясните их автору." : "Решение уже сохранено. Здесь можно прочитать результат."}</p>${p.status === "pending" ? `<form id="decision-form"><div class="field"><label for="decision-reason">Комментарий автору при возврате</label><textarea id="decision-reason" rows="4" placeholder="Что нужно исправить?"></textarea><span class="muted">Этот текст увидит автор публикации.</span></div><p class="error" id="decision-error" role="alert" hidden></p><div class="actions"><button type="button" class="primary" id="publish">Опубликовать</button><button type="submit" class="quiet">Вернуть автору</button></div></form>` : `<span class="tag success">${status(p.status)}</span><p>${esc(p.reason || "Публикация одобрена.")}</p><a class="quiet" href="#community">Вернуться к очереди</a>`}</section></div>`;
      const save = (s, reason = "") => {
        p.status = s;
        p.reason = reason;
        history.unshift(`${status(s)}: «${p.title}»`);
        render();
        notify(
          s === "published"
            ? "Материал опубликован. Очередь обновлена."
            : "Материал возвращён автору с вашим комментарием.",
        );
      };
      if (p.status === "pending") {
        document.getElementById("publish").onclick = () => save("published");
        document.getElementById("decision-form").onsubmit = (e) => {
          e.preventDefault();
          const reason = document
            .getElementById("decision-reason")
            .value.trim();
          if (!reason) {
            const err = document.getElementById("decision-error");
            err.textContent = "Напишите, что автору нужно исправить.";
            err.hidden = false;
            document.getElementById("decision-reason").focus();
            return;
          }
          save("returned", reason);
        };
      }
    } else if (route === "team") {
      main.innerHTML =
        head(
          "Команда и доступ",
          "Люди, их задачи и область работы.",
          `<a href="#grant" class="primary"><i class="fas fa-plus" aria-hidden="true"></i>Добавить сотрудника</a>`,
        ) +
        `<section class="panel"><h2>Рабочие назначения</h2>${team.map((t, i) => `<div class="row"><div class="row-main"><h3>${esc(t.name)}</h3><p>${esc(t.role)} · ${esc(t.scope)}</p><p class="muted">${esc(t.expires)}</p><div class="tags"><span class="tag ${t.active ? "success" : "neutral"}">${t.active ? "Активен" : "Доступ отозван"}</span></div></div>${t.active ? `<button class="danger revoke" data-index="${i}">Отозвать доступ</button>` : ""}</div>`).join("")}</section><section class="panel" style="margin-top:1rem"><h2>Владелец панели</h2><p>Разработчик IESA · все рабочие разделы</p><p class="muted">Последний владелец защищён от случайного отзыва. Выдача рабочей роли не открывает техническую админку Django.</p></section>`;
      main.querySelectorAll(".revoke").forEach(
        (b) =>
          (b.onclick = () => {
            pendingRevoke = Number(b.dataset.index);
            document.getElementById("confirm-title").textContent =
              `Отозвать доступ: ${team[pendingRevoke].name}?`;
            document.getElementById("confirm-copy").textContent =
              "Человек перестанет выполнять задачи этой роли. Его аккаунт участника сохранится.";
            document.getElementById("confirm-reason").value = "";
            document.getElementById("confirm").showModal();
          }),
      );
    } else if (route === "grant") {
      grant();
    } else {
      location.hash = "overview";
    }
  }
  function grant() {
    const r = roles[draft.role];
    main.innerHTML =
      `<div class="wizard"><a href="#team" class="back">К команде</a>` +
      head(
        "Добавить сотрудника",
        "Выберите человека, его задачи и проверьте итог.",
      ) +
      `<div class="steps" aria-label="Шаги назначения">${["Человек", "Работа", "Проверка"].map((s, i) => `<span class="${step === i + 1 ? "active" : ""}" ${step === i + 1 ? 'aria-current="step"' : ""}>${i + 1}. ${s}</span>`).join("")}</div><form id="grant-form" class="panel"><h2>${step === 1 ? "Кому вы выдаёте доступ?" : step === 2 ? "Какие задачи поручаете?" : "Проверьте доступ перед выдачей"}</h2><div id="step-fields">${step === 1 ? `<div class="field"><label for="person">Существующий аккаунт</label><select id="person">${["Мария Коваль", "Алексей Смирнов", "Елена Морозова"].map((n) => `<option ${n === draft.person ? "selected" : ""}>${n}</option>`).join("")}</select><span class="muted">В рабочей версии здесь будет поиск и проверка подтверждённого адреса.</span></div>` : step === 2 ? `<div class="field"><label for="role">Рабочая роль</label><select id="role"><option value="moderator" ${draft.role === "moderator" ? "selected" : ""}>Модератор сообщества</option><option value="partners" ${draft.role === "partners" ? "selected" : ""}>Менеджер партнёров</option></select></div><div id="role-details"></div><div class="field"><label for="expiry">Доступ до</label><input type="date" id="expiry" value="${esc(draft.expiry)}" min="2026-10-15" required><span class="muted">После этой даты назначение перестанет действовать.</span></div>` : `<div class="summary"><h3>${esc(draft.person)}</h3><p>${esc(r.name)} · ${draft.role === "partners" ? esc(draft.scope) : "Всё сообщество"}</p><p>До ${esc(draft.expiry.split("-").reverse().join("."))}</p><h3>Сможет</h3><ul>${r.allowed.map((x) => `<li>${esc(x)}</li>`).join("")}</ul><h3>Не получит</h3><ul>${r.denied.map((x) => `<li>${esc(x)}</li>`).join("")}</ul></div><div class="field"><label for="grant-reason">Почему нужен доступ?</label><textarea id="grant-reason" rows="3" required>${esc(draft.reason)}</textarea></div><label class="check"><input type="checkbox" id="checked" required><span>Я проверил человека, роль, область и срок.</span></label><p class="muted">В рабочей панели перед выдачей потребуется подтвердить личность. Сейчас реальные права не меняются.</p>`}</div><div class="actions">${step > 1 ? '<button type="button" class="quiet" id="previous">Назад</button>' : '<a class="quiet" href="#team">Отмена</a>'}<button type="submit" class="primary">${step < 3 ? "Продолжить" : "Выдать доступ"}</button></div></form></div>`;
    if (step === 2) {
      const details = () => {
        draft.role = document.getElementById("role").value;
        const r = roles[draft.role];
        document.getElementById("role-details").innerHTML =
          `<p class="muted">${r.allowed.map(esc).join(". ")}.</p>${draft.role === "partners" ? `<div class="field scope-fields"><label for="scope">Организация</label><select id="scope"><option ${draft.scope === "Alpine Club" ? "selected" : ""}>Alpine Club</option><option ${draft.scope === "Lake Sport" ? "selected" : ""}>Lake Sport</option></select><span class="muted">Только эта организация. Чужие данные останутся закрытыми.</span></div>` : '<p class="muted">Область: сообщество IESA. Контакты участников и управление доступом не открываются.</p>'}`;
      };
      document.getElementById("role").onchange = details;
      details();
    }
    const remember = () => {
      if (step === 1) draft.person = document.getElementById("person").value;
      if (step === 2) {
        draft.role = document.getElementById("role").value;
        draft.scope = document.getElementById("scope")?.value || draft.scope;
        draft.expiry = document.getElementById("expiry").value;
      }
      if (step === 3)
        draft.reason = document.getElementById("grant-reason").value;
    };
    if (step > 1)
      document.getElementById("previous").onclick = () => {
        remember();
        step--;
        grant();
      };
    document.getElementById("grant-form").onsubmit = (e) => {
      e.preventDefault();
      remember();
      if (step < 3) {
        step++;
        grant();
        main.focus();
      } else {
        const existing = team.find(
          (t) =>
            t.name === draft.person &&
            t.role === roles[draft.role].name &&
            t.scope ===
              (draft.role === "partners" ? draft.scope : "Всё сообщество") &&
            t.active,
        );
        if (existing) {
          notify("Такое назначение уже активно. Дубликат не создан.");
          return;
        }
        team.push({
          name: draft.person,
          role: roles[draft.role].name,
          scope: draft.role === "partners" ? draft.scope : "Всё сообщество",
          expires: "До " + draft.expiry.split("-").reverse().join("."),
          active: true,
        });
        history.unshift("Выдан доступ: " + draft.person);
        step = 1;
        nextNotice = "Рабочее назначение создано в демонстрации.";
        location.hash = "team";
      }
    };
  }
  function menu() {
    const nav = document.getElementById("side-nav");
    const open = nav.classList.toggle("open");
    document
      .getElementById("menu-toggle")
      .setAttribute("aria-expanded", String(open));
  }
  document.getElementById("menu-toggle").onclick = menu;
  document.getElementById("mobile-sections").onclick = menu;
  document.addEventListener("keydown", (e) => {
    if (
      e.key === "Escape" &&
      document.getElementById("side-nav").classList.contains("open")
    )
      menu();
  });
  document.getElementById("confirm-cancel").onclick = () =>
    document.getElementById("confirm").close();
  document.getElementById("confirm-form").onsubmit = (e) => {
    e.preventDefault();
    team[pendingRevoke].active = false;
    history.unshift("Отозван доступ: " + team[pendingRevoke].name);
    document.getElementById("confirm").close();
    render();
    notify("Доступ отозван. Аккаунт участника сохранён.");
  };
  document.querySelector(".skip").onclick = (e) => {
    e.preventDefault();
    main.focus();
  };
  window.addEventListener("hashchange", () => {
    document.getElementById("notice").hidden = true;
    document.getElementById("side-nav").classList.remove("open");
    document
      .getElementById("menu-toggle")
      .setAttribute("aria-expanded", "false");
    render();
    main.focus();
    if (nextNotice) {
      notify(nextNotice);
      nextNotice = "";
    }
  });
  persona.onchange = () => {
    render();
    notify(
      persona.value === "moderator"
        ? "Модератор видит свои задачи. Управление доступом скрыто."
        : "Показаны возможности владельца панели.",
    );
  };
  render();
})();
