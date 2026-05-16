async function loadJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`${path} を読み込めませんでした`);
  }
  return response.json();
}

function getByPath(object, path) {
  return path.split(".").reduce((current, key) => {
    if (current == null) return undefined;
    return current[key];
  }, object);
}

function setHref(selector, value) {
  document.querySelectorAll(selector).forEach((el) => {
    if (value) el.href = value;
  });
}

function applyTextConfig(config) {
  document.querySelectorAll("[data-config]").forEach((el) => {
    const key = el.dataset.config;
    if (key === "dateTimeText") return;
    const value = getByPath(config, key);
    if (value !== undefined && value !== null && value !== "") {
      el.textContent = value;
    }
  });

  document.querySelectorAll("[data-meta-config]").forEach((el) => {
    const value = getByPath(config, el.dataset.metaConfig);
    if (value !== undefined && value !== null && value !== "") {
      el.setAttribute("content", value);
    }
  });
}

function setDateTimeText(value) {
  document.querySelectorAll('[data-config="dateTimeText"]').forEach((el) => {
    if (!value) return;

    const parts = value.split("／").filter(Boolean);
    let year = "";

    if (parts.length > 0) {
      const match = parts[0].match(/^([0-9]{4}年)(.*)$/);
      if (match) {
        year = match[1];
        parts[0] = match[2];
      }
    }

    if (!year && parts[0] && /^[0-9]{4}年$/.test(parts[0])) {
      year = parts.shift();
    }

    const lines = [];
    if (year) {
      lines.push(`<span class="date-year-full">${year}</span>`);
    }
    parts.forEach((part) => {
      lines.push(`<span class="date-main">${part}</span>`);
    });

    el.innerHTML = lines.join("");
    el.classList.add("date-time-lines");
  });
}

function createExternalIframe(src, title) {
  const iframe = document.createElement("iframe");
  iframe.src = src;
  iframe.title = title;
  iframe.loading = "lazy";
  iframe.referrerPolicy = "no-referrer-when-downgrade";
  iframe.allowFullscreen = true;
  return iframe;
}

function normalizeGoogleMapLink(config) {
  const links = config.links || {};
  const normalizedLinks = { ...links };

  const venueQuery = encodeURIComponent(config.venueName || "会場未定");
  if (
    !normalizedLinks.googleMap ||
    /google\.com\/maps\/embed/.test(normalizedLinks.googleMap)
  ) {
    normalizedLinks.googleMap = `https://www.google.com/maps/search/?api=1&query=${venueQuery}`;
  }

  return normalizedLinks;
}

function renderOrganizerMembers(config) {
  const members = config.organizer?.members || [];
  const membersBlock = document.getElementById("organizer-members");
  const membersList = document.getElementById("organizer-members-list");

  if (!membersBlock || !membersList || members.length === 0) return;

  membersList.innerHTML = "";

  const roleGroups = new Map();
  const addMember = (role, name) => {
    if (!name) return;
    const roleName = role || "運営メンバー";
    if (!roleGroups.has(roleName)) roleGroups.set(roleName, []);
    roleGroups.get(roleName).push(name);
  };

  members.forEach((member) => {
    if (typeof member === "string") {
      addMember("運営メンバー", member);
    } else {
      addMember(member.role || member.group || "運営メンバー", member.name || "");
    }
  });

  roleGroups.forEach((names, role) => {
    const li = document.createElement("li");
    li.className = "member-group";

    const namesWrap = document.createElement("span");
    namesWrap.className = "member-names";

    names.forEach((name) => {
      const chip = document.createElement("span");
      chip.className = "member-chip";
      chip.textContent = name;
      namesWrap.appendChild(chip);
    });

    if (role !== "運営メンバー") {
      const roleLabel = document.createElement("span");
      roleLabel.className = "member-role";
      roleLabel.textContent = role;
      li.appendChild(roleLabel);
    } else {
      li.classList.add("member-group-no-role");
    }

    li.appendChild(namesWrap);
    membersList.appendChild(li);
  });

  membersBlock.hidden = false;
}

async function applyConfig() {
  try {
    const config = await loadJson("data/config.json");

    applyTextConfig(config);
    setDateTimeText(config.dateTimeText);

    const links = normalizeGoogleMapLink(config);
    Object.entries(links).forEach(([key, value]) => {
      setHref(`[data-link="${key}"]`, value);
    });

    const sns = config.sns || {};
    Object.entries(sns).forEach(([key, value]) => {
      setHref(`[data-sns="${key}"]`, value);
    });

    const mapContainer = document.getElementById("map-container");
    if (mapContainer && links.mapEmbed) {
      mapContainer.innerHTML = "";
      mapContainer.appendChild(createExternalIframe(links.mapEmbed, "会場のGoogle Map"));
    }

    const videoContainer = document.getElementById("video-container");
    if (videoContainer && links.youtubeEmbed) {
      videoContainer.innerHTML = "";
      const iframe = createExternalIframe(links.youtubeEmbed, "紹介動画");
      iframe.allow = "accelerometer; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen";
      videoContainer.appendChild(iframe);
    }

    renderOrganizerMembers(config);
  } catch (error) {
    console.error(error);
  }
}

document.addEventListener("DOMContentLoaded", applyConfig);
