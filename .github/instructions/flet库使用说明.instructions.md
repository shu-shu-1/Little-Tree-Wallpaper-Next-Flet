---
applyTo: '**'
---

由于flet库更新过快，在编写代码前请注意查看文档：
https://docs.flet.dev/controls/

常见不兼容性更改：


    Alignment: use ft.Alignment.CENTER (and other Alignment constants) instead of ft.alignment.center。
    scroll_to(): key renamed to scroll_key; in control key should be key=ft.ScrollKey(<value>)
    ScrollableControl: on_scroll_interval renamed to scroll_interval
    Animation: instead of ft.animation.Animation use ft.Animation
    Tabs: instead of text: OptionalString 和 tab_content: Optional[Control] use label: Optional[StrOrControl])
    Pagelet: bottom_app_bar renamed to bottom_appbar
    page.client_storage changed to page.shared_preferences。
    Dialogs: page.show_dialog(dialog_name) instead of page.open(dialog_name); `page.pop_dialog() to close dialog
    NavigationDrawer: position property instead of page.drawer 和 page.end_drawer
    All buttons: no text property, use content instead
    NavigationRailDesctination: no label_content property, use label instead
    SafeArea.left, .top, .right, .bottom to SafeArea.avoid_intrusions_left, .avoid_intrusions_top, .avoid_intrusions_right, .avoid_intrusions_bottom.
    Badge: use label instead of text
    Padding, Margin: should have named, not positional arguments. For example, instead of ft.Padding.symmetric(0, 10) should be ft.Padding(vertical = 0, horizontal = 10)
    SegmentedButton: selected: List[str] instead of Optional[Set]. Example: selected=["1", "4"] instead of selected={"1", "4"}. TODO: support sets in flet V1
    CupertinoActionSheetAction, CupertinoDialogAction, CupertinoContextMenuAction: default instead of is_default_action; destructive instead of is_destructive_action
    ft.app(target=main) should be changed to ft.run(main) 或 ft.run(main=main)。
    FilePicker is a service now and must be added to page.services to work. Also, it provides only async methods to open dialogs which return results right away -no "on_result" event anymore.
    DragTarget.on_will_accept is of DragWillAcceptEvent type with accept: bool field. Use e.accept instead of e.data. DragTarget.on_leave is of DragTargetLeaveEvent type with src_id field. Use e.src_id instead of e.data。
    Page.on_resized renamed to Page.on_resize。
    Card.color -> Card.bgcolor， Card.is_semantic_container -> Card.semantic_container
    Checkbox.is_error -> Checkbox.error。
    Chip.click_elevation -> Chip.press_elevation
    Markdown.img_error_content -> Markdown.image_error_content。
    Switch.label_style -> Switch.label_text_style。
    Tabs.is_secondary -> Tabs.secondary。
    BoxDecoration.shadow -> BoxDecoration.shadows。
    canvas.Text.text -> canvas.Text.value。
    Remove _async suffix from all methods, remove fire-n-forget counterparts
    Icon.name -> Icon.icon。
    Dropdown.on_change is now triggered when text entered in editable mode; a new on_select event is triggered when an item selected from the list.
    移除 primary_swatch (use color_scheme_seed), primary_color (use ColorScheme.primary), primary_color_dark， primary_color_light， shadow_color (use ColorScheme.shadow), divider_color (use in DividerTheme.color) from Theme。
