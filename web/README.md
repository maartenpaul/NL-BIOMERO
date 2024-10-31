# NL-BIOMERO Web Container
Welcome to the NL-BIOMERO Web Container, a specialized deployment of OMERO tailored for the [Cellular Imaging lab at Amsterdam University Medical Center](https://github.com/Cellular-Imaging-Amsterdam-UMC). This deployment includes several customizations to enhance the user experience and functionality of the OMERO web interface. 

To get started, ensure you have Docker installed on your system and access to the NL-BIOMERO Docker image. This deployment includes the following customizations, located in the `omeroweb_edits` folder:

- **omero-database-pages**: Adds additional pages to the OMERO web interface for better database interaction and visualization.
- **better_buttons**: Enhances the user interface by providing more intuitive and accessible buttons for common actions.
- **pretty_login***: Improves the login page aesthetics for a more welcoming and user-friendly experience.

## OMERO Database Pages
OMERO Database Pages introduces additional pages accessible via buttons available in the middle_header to the OMERO web interface. The pages are dedicated to embedding iframe views of metabase dashboards. The Imports and Workflow pages showcase the history and status of imports and workflows run by each user respectively. Administrators have access to the metabase interface, whereas non-admin users are restricted to their own imports and workflows. IMPORTANT: This add-on relies on the metabase container and requires configuring the metabase server. See the [metabase documentation](../metabase/README.md) for more details.


## Better Buttons
Enhances the OMERO web interface by providing more intuitive and accessible buttons for common actions and improves the fluidity of group and user selection. It achieves this by editing some button names via the `web/local_omeroweb_edits/01-default-webapps.omero` configuration file, and by overriding default files of omero web during the build process:
- `./webclient/templates/webclient/base/includes/group_user_dropdown2.html` 
- `./webclient/static/webclient/css/layout.css`
- `./webclient/templates/webclient/data/containers.html`
- `./webclient/templates/webclient/public/public.html`
- `./webgateway/static/webgateway/css/ome.header.css`

**Imporvement list with before and afters**
- Renames the default titles of buttons (defined in .omero config file)
- From the middle_header removes unnecessary buttons like 'History' as its functionality is replaced by Database Pages. 
- From the middle_header replaced 'Any Value' title with more intuitive 'Annotation Search' title.
- Added functionality that constricts the top corner OMERO title and icon to leave more room for middle_header buttons
    ![middle_header before](/web/Documentation/Images/middle_header_before.PNG)
    ![middle_header after](/web/Documentation/Images/middle_header_after.PNG)
- From the left_panel_toolbar: Removes Shares tab (discontinued functionality), and Create Share button from left_panel_toolbar.
- Improved group_user_selection by adding 'Group Select' button title for clarity, as the original button is not recognizable as a button by new users.
- Added functionality that enable double-clicking on a group name in the dropdown_menu to go directly to 'All_Members' of said group.
    ![group_user_selection before](/web/Documentation/Images/left_pange_toolbar_before.PNG)
    ![group_user_selection after](/web/Documentation/Images/left_pange_toolbar_after.PNG)

## Pretty Login
Focuses on improving the aesthetics of the login page, creating a more welcoming and user-friendly experience. This enhancement is part of our effort to make the interface more appealing and easier to navigate for all users. The deployment of this add on overrides the following files:
- `./webclient/templates/webclient/login.html` (updated via script)
- `./webclient/static/webclient/image/login_page_images/` (directory populated with images)
- `./webgateway/static/webgateway/css/ome.login.css`

**Imporvement list with before and afters**
- Removed the server choice which is not useful for common users and redundant for admins
- Planced the 'OMERO.web' banner neatly inside the brighter window
- Added space for documentation which users may need to access even before logging in.

    ![login_page before](/web/Documentation/Images/login_page_before.PNG)
    ![login_page after](/web/Documentation/Images/login_page_after.PNG)


## Troubleshooting

## Contributing

We welcome contributions to improve NL-BIOMERO. Please fork the repository and submit a pull request with your changes.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

## Contact

For questions or support, please contact the Cellular Imaging lab at Amsterdam University Medical Center.

---

Thank you for using NL-BIOMERO!