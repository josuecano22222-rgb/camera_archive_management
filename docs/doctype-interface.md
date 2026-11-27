# DocType views and form layout

Frappe v15 supplies List, Report Builder, Dashboard, and (except for File) Kanban views through its standard List View switcher. Kanban boards are user-created and depend on a boardable Select field; this app does not seed database records or user-specific boards as fixtures.

The app enables other views only where the DocType has the data shape they need:

| DocType | Additional view(s) | Basis |
| --- | --- | --- |
| CAM Vehicle | Image | Existing `vehicle_list_image` image field. |
| Vehicle Type | Image | Existing `vehicle_type_image` attachment. |
| Camera | Image, Map | Main image is stored on Camera for the native Image view; location and coordinates support Map view. |
| Camera Area | Tree | Existing nested-set hierarchy and parent field. |
| Geo Admin Area | Tree, Map | Existing nested-set hierarchy and latitude/longitude. |
| Geo Boundary | Map | Permission-filtered centroid markers using the boundary-specific centroid fields. |
| Geo Gazetteer Place | Map | Existing latitude/longitude. |
| Motion Event | Map | Permission-filtered event snapshot coordinates. |

Geo Boundary and Motion Event use a small permission-filtered adapter for their nonstandard centroid / snapshot coordinate fields; invalid or blank coordinate pairs are skipped. Motion Event is a point-in-time event with no end field; because Frappe v15 couples Calendar and Gantt availability to the same calendar configuration, it is not given a misleading editable Gantt interval.

Form fields for substantive records are grouped into workflow tabs and labeled sections. Camera images are an ordered gallery without an application-imposed image-count cap and stored on the Camera record, with captions, one main image, and native Frappe File attachments for the binary content; the former Camera Photo child DocType is retired by a fail-closed, data-preserving migration. The map renders the selected main image as a circular portrait with a pin tip anchored at the camera coordinates, and includes country-boundary context, layer controls, movement replay, geodesic measuring tools, coordinate copy, and browser-local geolocation. Generalized Natural Earth country outlines and classification catalogs are additive core data; sample records are a separate, explicit opt-in scenario that can be created on any site by an authorized operator and are excluded from the map by default. Other inline child-table DocTypes remain compact so grid editing is not burdened with nested tabs. Frappe-managed nested-set maintenance fields on Camera Area and Geo Admin Area are hidden from routine form editing.
