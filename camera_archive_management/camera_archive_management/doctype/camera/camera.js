frappe.ui.form.on("Camera", {
	refresh(frm) {
		render_camera_gallery(frm);
		if (frm.is_new()) return;
		frm.add_custom_button(__("Open map"), () => {
			frappe.route_options = { camera: frm.doc.name, view: "camera" };
			frappe.set_route("camera-archive-map");
		}, __("Camera Archive"));
	},
});

const CAMERA_IMAGE_EXTENSIONS = new Set([
	"avif", "bmp", "gif", "jpeg", "jpg", "png", "tif", "tiff", "webp",
]);

function read_camera_gallery(frm) {
	try {
		const gallery = JSON.parse(frm.doc.camera_photos_json || "[]");
		return Array.isArray(gallery) ? gallery : [];
	} catch (_error) {
		return [];
	}
}

function set_camera_gallery(frm, gallery) {
	gallery = gallery.map((photo, index) => ({ ...photo, sort_order: index }));
	if (gallery.length && !gallery.some((photo) => photo.is_primary)) {
		gallery[0].is_primary = true;
	}
	return frm
		.set_value("camera_photos_json", JSON.stringify(gallery))
		.then(() => frm.set_value("primary_image", gallery.find((photo) => photo.is_primary)?.url || ""))
		.then(() => render_camera_gallery(frm));
}

function make_gallery_button(label, class_name, handler, disabled = false) {
	const button = document.createElement("button");
	button.type = "button";
	button.className = `btn btn-xs ${class_name}`;
	button.textContent = label;
	button.disabled = disabled;
	button.addEventListener("click", handler);
	return button;
}

function render_camera_gallery(frm) {
	const wrapper = frm.fields_dict.camera_photo_gallery?.$wrapper?.get(0);
	if (!wrapper) return;
	wrapper.replaceChildren();

	const gallery = read_camera_gallery(frm)
		.filter((photo) => photo && typeof photo.url === "string" && /^\/(?:private\/)?files\//.test(photo.url))
		.sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0));
	const can_write = Boolean(frm.perm?.[0]?.write);
	const panel = document.createElement("div");
	panel.className = "cam-photo-gallery-editor";

	const toolbar = document.createElement("div");
	toolbar.className = "cam-photo-gallery-toolbar";
	const summary = document.createElement("span");
	summary.className = "text-muted";
	summary.textContent = gallery.length
		? __("{0} images · choose one main image", [gallery.length])
		: __("No camera images yet. Add a photo to create the map pin portrait.");
	toolbar.append(summary);

	if (can_write) {
		const add = make_gallery_button(
			__("Add image"),
			"btn-primary",
			() => {
				if (frm.is_new()) {
					frappe.show_alert({ message: __("Save the Camera before uploading images."), indicator: "orange" });
					return;
				}
				new frappe.ui.FileUploader({
					doctype: "Camera",
					docname: frm.docname,
					allow_multiple: false,
					is_private: 1,
					restrictions: { allowed_file_types: ["image/*"] },
					on_success(file_doc) {
						const file = file_doc?.message || file_doc;
						const url = file?.file_url;
						const extension = (file?.file_name || "").split(".").pop().toLowerCase();
						if (!url || !/^\/(?:private\/)?files\//.test(url) || !CAMERA_IMAGE_EXTENSIONS.has(extension)) {
						frappe.msgprint(__("Choose a supported image file (JPEG, PNG, WebP, GIF, TIFF, BMP, or AVIF)."));
						return;
					}
					if (read_camera_gallery(frm).some((photo) => photo.url === url)) return;
					const updated = read_camera_gallery(frm);
					updated.push({
						url,
						caption: (file.file_name || "").replace(/\.[^.]+$/, ""),
						description: "",
						is_primary: updated.length === 0,
						sort_order: updated.length,
					});
					set_camera_gallery(frm, updated);
				},
				});
			},
			frm.is_new()
		);
		toolbar.append(add);
	}
	panel.append(toolbar);

	const note = document.createElement("p");
	note.className = "text-muted cam-photo-gallery-note";
	note.textContent = frm.is_new()
		? __("Save the Camera before uploading images.")
		: __("Gallery changes save with the Camera record. Removing an image here does not delete its Frappe File.");
	panel.append(note);

	const cards = document.createElement("div");
	cards.className = "cam-photo-gallery-grid";
	gallery.forEach((photo, index) => {
		const card = document.createElement("article");
		card.className = `cam-photo-card${photo.is_primary ? " is-main" : ""}`;
		const image = document.createElement("img");
		image.src = photo.url;
		image.alt = photo.caption || frm.doc.camera_name || __("Camera image");
		image.loading = "lazy";
		image.referrerPolicy = "same-origin";
		card.append(image);

		const badge = document.createElement("span");
		badge.className = "cam-photo-main-badge";
		badge.textContent = photo.is_primary ? __("MAIN IMAGE") : `${index + 1}`;
		card.append(badge);

		if (can_write) {
			const caption = document.createElement("input");
			caption.type = "text";
			caption.maxLength = 240;
			caption.className = "form-control input-xs cam-photo-caption";
			caption.placeholder = __("Caption");
			caption.value = photo.caption || "";
			caption.addEventListener("change", () => {
				const updated = read_camera_gallery(frm);
				updated[index].caption = caption.value;
				set_camera_gallery(frm, updated);
			});
			card.append(caption);

			const actions = document.createElement("div");
			actions.className = "cam-photo-actions";
			if (!photo.is_primary) {
				actions.append(make_gallery_button(__("Make main"), "btn-default", () => {
					const updated = read_camera_gallery(frm);
					updated.forEach((item, item_index) => { item.is_primary = item_index === index; });
					set_camera_gallery(frm, updated);
				}));
			}
			actions.append(make_gallery_button("↑", "btn-default", () => {
				if (index === 0) return;
				const updated = read_camera_gallery(frm);
				[updated[index - 1], updated[index]] = [updated[index], updated[index - 1]];
				set_camera_gallery(frm, updated);
			}, index === 0));
			actions.append(make_gallery_button("↓", "btn-default", () => {
				if (index >= gallery.length - 1) return;
				const updated = read_camera_gallery(frm);
				[updated[index], updated[index + 1]] = [updated[index + 1], updated[index]];
				set_camera_gallery(frm, updated);
			}, index >= gallery.length - 1));
			actions.append(make_gallery_button(__("Remove"), "btn-danger", () => {
				const updated = read_camera_gallery(frm).filter((_item, item_index) => item_index !== index);
				if (updated.length && !updated.some((item) => item.is_primary)) updated[0].is_primary = true;
				set_camera_gallery(frm, updated);
			}));
			card.append(actions);
		}
		cards.append(card);
	});
	panel.append(cards);
	wrapper.append(panel);
}
