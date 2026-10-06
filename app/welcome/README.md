# welcome/

The front page: the name, two sentences on the game, the Play button (`../play/`), the controls, and a live box fed by `GET ../api/summary` every 5 seconds: people (`playing`) and bots (`bots`) in the arena, the round standings (name, frags, deaths, bots marked) and the time the round has left (`round.ends` minus `now`, both server clock, counted down locally between fetches). If the fetch fails the box says the arena is asleep.

`#signin` is an empty placeholder where the Endless Mind sign-in box will be mounted later. Styles: `../shared/base.css` plus `welcome.css`. Plain HTML, CSS and an ES module; page-relative URLs only.
